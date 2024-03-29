import torch
from torch import nn
from torchstat import stat  # 查看网络参数
from torchsummary import summary  # 查看网络结构
import torch.nn.functional as F
import numpy as np

# -------------------------------------------- #
# （1）残差单元
# x--> 卷积 --> bn --> relu --> 卷积 --> bn --> 输出
# |---------------Identity(短接)----------------|
'''
in_channel   输入特征图的通道数 
out_channel  第一次卷积输出特征图的通道数
stride=1     卷积块中3*3卷积的步长
downsample   是否下采样
'''


# -------------------------------------------- #
# 适配于resnet50, 101, 152
class Bottleneck(nn.Module):
    # 最后一个1*1卷积下降的通道数
    expansion = 4

    # 初始化
    def __init__(self, in_channel, out_channel, stride=1, downsample=None):
        # 继承父类初始化方法
        super(Bottleneck, self).__init__()

        # 属性分配
        # 1*1卷积下降通道，padding='same'，若stride=1，则[b,in_channel,h,w]==>[b,out_channel,h,w]
        self.conv1 = nn.Conv2d(in_channels=in_channel, out_channels=out_channel,
                               kernel_size=1, stride=1, padding=0, bias=False)

        # BN层是计算特征图在每个channel上面的均值和方差，需要给出输出通道数
        self.bn1 = nn.BatchNorm2d(out_channel)

        # relu激活, inplace=True节约内存
        # self.relu = nn.ReLU(inplace=True)
        self.relu = nn.PReLU()

        # 3*3卷积提取特征，[b,out_channel,h,w]==>[b,out_channel,h,w]
        self.conv2 = nn.Conv2d(in_channels=out_channel, out_channels=out_channel,
                               kernel_size=3, stride=stride, padding=1, bias=False)

        # BN层, 有bn层就不需要bias偏置
        self.bn2 = nn.BatchNorm2d(out_channel)

        # 1*1卷积上升通道 [b,out_channel,h,w]==>[b,out_channel*expansion,h,w]
        self.conv3 = nn.Conv2d(in_channels=out_channel, out_channels=out_channel * self.expansion,
                               kernel_size=1, stride=1, padding=0, bias=False)

        # BN层，对out_channel*expansion标准化
        self.bn3 = nn.BatchNorm2d(out_channel * self.expansion)

        # 记录是否需要下采样, 下采样就是第一个卷积层的步长=2，输入和输出的图像的尺寸不一致
        self.downsample = downsample

    # 前向传播
    def forward(self, x):
        # 残差边
        identity = x

        # 如果第一个卷积层stride=2下采样了，那么残差边也需要下采样
        if self.downsample is not None:
            # 下采样方法
            identity = self.downsample(x)

        # 主干部分
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu(x)

        x = self.conv3(x)
        x = self.bn3(x)

        # 残差连接
        x = x + identity
        # relu激活
        x = self.relu(x)

        return x  # 输出残差单元的结果


"""
适配于resnet 18,34
"""
class Bottleneck_small(nn.Module):
    # 最后一个1*1卷积下降的通道数
    expansion = 1

    # 初始化
    def __init__(self, in_channel, out_channel, stride=1, downsample=None):
        # 继承父类初始化方法  继承了nn.Module中的一些方法，使之可以被调用，如eval,train等
        super(Bottleneck_small, self).__init__()

        # 属性分配
        # 3*3卷积提取特征
        self.conv1 = nn.Conv2d(in_channels=in_channel, out_channels=out_channel,
                               kernel_size=3, stride=stride, padding=1, bias=False)

        # BN层, 有bn层就不需要bias偏置
        self.bn1 = nn.BatchNorm2d(out_channel)

        # relu激活, inplace=True节约内存
        # self.relu = nn.ReLU(inplace=True)
        self.relu = nn.PReLU()

        # 3*3卷积
        self.conv2 = nn.Conv2d(in_channels=out_channel, out_channels=out_channel * self.expansion,
                               kernel_size=3, stride=1, padding=1, bias=False)

        # BN层，对out_channel*expansion标准化
        self.bn2 = nn.BatchNorm2d(out_channel * self.expansion)

        # 记录是否需要下采样, 下采样就是第一个卷积层的步长=2，输入和输出的图像的尺寸不一致
        self.downsample = downsample

    # 前向传播
    def forward(self, x):
        # 残差边
        identity = x

        # 如果第一个卷积层stride=2下采样了，那么残差边也需要下采样
        if self.downsample is not None:
            # 下采样方法
            identity = self.downsample(x)

        # 主干部分
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)

        # 残差连接
        x = x + identity
        # relu激活
        x = self.relu(x)

        return x  # 输出残差单元的结果


# -------------------------------------------- #
# （2）网络构建
'''
block： 残差单元
blocks_num： 每个残差结构使用残差单元的数量
num_classes： 分类数量
include_top： 是否包含分类层（全连接）
'''


# -------------------------------------------- #
class ResNet(nn.Module):
    # 初始化
    def __init__(self, block, blocks_num, num_classes=2, include_top=True, dropout=0.4):
        # 继承父类初始化方法
        super(ResNet, self).__init__()

        # 属性分配
        self.dropout = dropout
        self.include_top = include_top
        self.in_channel = 64  # 第一个卷积层的输出通道数
        self.first_channel = 3  # 在未经过卷积之前的输入通道数

        # 7*7卷积下采样层处理输入图像 [b,3,h,w]==>[b,64,h//2,w//2]
        self.conv1 = nn.Conv2d(in_channels=3, out_channels=self.in_channel,
                               kernel_size=7, stride=2, padding=3, bias=False)

        # BN对每个通道做标准化
        self.bn1 = nn.BatchNorm2d(self.in_channel)
        # self.bn_first = nn.BatchNorm2d(self.first_channel)

        # relu激活函数
        # self.relu = nn.ReLU(inplace=True)
        self.relu = nn.PReLU()

        # 3*3最大池化层 [b,64,h//2,w//2]==>[b,64,h//4,w//4]
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        # 残差卷积块
        # 第一个残差结构不需要下采样只需要调整通道
        self.layer1 = self._make_layer(block, 64, blocks_num[0])
        # 下面的残差结构的第一个残差单元需要进行下采样
        self.layer2 = self._make_layer(block, 128, blocks_num[1], stride=2)
        self.layer3 = self._make_layer(block, 256, blocks_num[2], stride=2)
        self.layer4 = self._make_layer(block, 512, blocks_num[3], stride=2)

        self.softmax = nn.Softmax(dim=1)

        # 分类层
        if self.include_top:
            # 自适应全局平均池化，无论输入特征图的shape是多少，输出特征图的(h,w)==(1,1)
            self.avgpool = nn.AdaptiveAvgPool2d((1, 1))  # output
            # 全连接分类
            self.fc = nn.Linear(512 * block.expansion, num_classes)

        # 卷积层权重初始化
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out')

    # 残差结构
    '''
    block: 代表残差单元
    channel: 残差结构中第一个卷积层的输出通道数
    block_num: 代表一个残差结构包含多少个残差单元
    stride: 是否下采样stride=2
    '''

    def _make_layer(self, block, channel, block_num, stride=1):

        # 是否需要进行下采样
        downsample = None

        # 如果stride=2或者残差单元的输入和输出通道数不一致
        # 就对残差单元的shortcut部分执行下采样操作
        if stride != 1 or self.in_channel != channel * block.expansion:
            # 残差边需要下采样
            downsample = nn.Sequential(
                # 对于第一个残差单元的残差边部分只需要调整通道
                nn.Conv2d(in_channels=self.in_channel, out_channels=channel * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(channel * block.expansion))

        # 一个残差结构堆叠多个残差单元
        layers = []
        # 先堆叠第一个残差单元，因为这个需要下采样
        layers.append(block(self.in_channel, channel, stride=stride, downsample=downsample))

        # 获得第一个残差单元的输出特征图个数, 作为第二个残差单元的输入
        self.in_channel = channel * block.expansion

        # 堆叠剩下的残差单元，此时的shortcut部分不需要下采样
        for _ in range(1, block_num):
            layers.append(block(self.in_channel, channel))

        # 返回构建好了的残差结构
        return nn.Sequential(*layers)  # *代表将layers以非关键字参数的形式返还

    # 前向传播
    def forward(self, x):
        # 输入层
        # 建议在输入卷积之前先bn一下
        # x = self.bn_first(x)
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        # 残差结构
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        """
        全连接层加在dropout之后的
        证实了，这个是对的
        """
        # 分类层
        if self.include_top:
            # 全局平均池化
            x = self.avgpool(x)
            # 打平
            x = torch.flatten(x, 1)
            if self.dropout > 0.:
                x = F.dropout(x, p=self.dropout, training=self.training)
                # print(self.training)
            # 全连接分类
            x = self.fc(x)
            # 是不是应该加一层softmax
            # x = self.softmax(x)

        return x


# 构建resnet50
def resnet50(num_classes=2, include_top=True, dropout=0.2):
    return ResNet(Bottleneck, [3, 4, 6, 3], num_classes=num_classes, include_top=include_top, dropout=dropout)


def resnet18(num_classes=2, include_top=True, dropout=0.2):
    return ResNet(Bottleneck_small, [2, 2, 2, 2], num_classes=num_classes, include_top=include_top, dropout=dropout)


def resnet34(num_classes=2, include_top=True, dropout=0.2):
    return ResNet(Bottleneck_small, [3, 4, 6, 3], num_classes=num_classes, include_top=include_top, dropout=dropout)


if __name__ == '__main__':
    # 接收网络模型
    model = resnet18()
    # print(model)

    # 查看网络参数量，不需要指定输入特征图像的batch维度
    stat(model, input_size=(3, 224, 224))

    # 查看网络结构及参数
    summary(model, input_size=[(3, 224, 224)], device='cpu')