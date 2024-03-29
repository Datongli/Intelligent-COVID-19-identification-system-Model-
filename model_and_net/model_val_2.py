"""
此文件用于替换掉数据的预处理部分，使用每张图片的均值和方差
而不是像model_val_1一样使用的是统一将均值和方差都归一化到0.5
"""
import os
import torch
from torchvision import transforms
from PIL import Image
import ResNet
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc
import numpy as np
import datetime
import itertools
import eca_ResNet
import GhostNet
import imageio.v2 as imageio

negative = "negative"
positive = "positive"


def count_mean_std(filepath):
    """
    :param filepath: 传入的单张图片的地址
    :return: 返回计算的方差和均值
    """
    R_channel = 0
    G_channel = 0
    B_channel = 0

    img = imageio.imread(filepath) / 255.0
    R_channel = R_channel + np.sum(img[:, :, 0])
    G_channel = G_channel + np.sum(img[:, :, 1])
    B_channel = B_channel + np.sum(img[:, :, 2])

    num = 224 * 224  # 这里（512,512）是每幅图片的大小，所有图片尺寸都一样
    R_mean = R_channel / num
    G_mean = G_channel / num
    B_mean = B_channel / num

    R_channel = 0
    G_channel = 0
    B_channel = 0

    img = imageio.imread(filepath) / 255.0
    R_channel = R_channel + np.sum((img[:, :, 0] - R_mean) ** 2)
    G_channel = G_channel + np.sum((img[:, :, 1] - G_mean) ** 2)
    B_channel = B_channel + np.sum((img[:, :, 2] - B_mean) ** 2)

    R_var = np.sqrt(R_channel / num)
    G_var = np.sqrt(G_channel / num)
    B_var = np.sqrt(B_channel / num)
    # print("R_mean is %f, G_mean is %f, B_mean is %f" % (R_mean, G_mean, B_mean))
    # print("R_var is %f, G_var is %f, B_var is %f" % (R_var, G_var, B_var))
    mean = [R_mean, G_mean, B_mean]
    std = [R_var, G_var, B_var]
    return mean, std

# 加时间戳
nowTime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
# -------------------------------------------------- #
# （0）参数设置
# -------------------------------------------------- #
# 权重参数路径
weights_path = r"C:\Users\ldt20\Desktop\训练权重保存\Track1+CoughVid logMel train_val ResNet18网络.pth"

# 图片文件路径
img_dir_path = r"D:\学习\大创\data\训练数据集\data\自建数据集\logMel_zj"
# dir_count = img_dir_path.rfind('/') + 1
# dir_path = img_dir_path[dir_count:]
dir_path = os.path.basename(img_dir_path)
cd = os.path.exists("D:/学习/大创/data/训练数据集/model/photo/" + dir_path)
if cd:
    print("保存文件夹已存在")
else:
    print("创建保存文件夹")
    os.mkdir("D:/学习/大创/data/训练数据集/model/photo/" + dir_path)

# weights_path = "D:/学习/大创/data/训练数据集/model/pth/melspec(1000_50)/model_melspec(1000_50)最好的权重.pth"
# 预测索引对应的类别名称
# class_names = ['cat', 'dog']
class_names = [negative, positive]
image_len = len(os.listdir(os.path.join(img_dir_path, negative)))
image_len += len(os.listdir(os.path.join(img_dir_path, positive)))
print("一共校验了" + str(image_len) + "张图片")

# 获取GPU设备
if torch.cuda.is_available():  # 如果有GPU就用，没有就用CPU
    device = torch.device('cuda:0')
else:
    device = torch.device('cpu')

# -------------------------------------------------- #
# （1）数据加载
# -------------------------------------------------- #
# 数据预处理
# 加载模型
model = ResNet.resnet18(num_classes=2, include_top=True)
# model = GhostNet.ghostnet()
# model = eca_ResNet.eca_resnet18(num_classes=2)
# 加载权重文件
model.load_state_dict(torch.load(weights_path, map_location=device))
# 模型切换成验证模式，dropout和bn切换形式
model.eval()
# 前向传播过程中不计算梯度
predict_clas = []
predict_scores = []
predict_names = []
pre_score = []
ture_labels = []
image = []
acc = 0.0
frames = []
# 初始化混淆矩阵
cnf_matrix = np.zeros([2, 2])

for img_path in os.listdir(img_dir_path):
    if img_path == negative:
        label = negative
    else:
        label = positive

    for photo_img in os.listdir(os.path.join(img_dir_path, img_path)):
        img_path0 = os.path.join(img_dir_path, img_path, photo_img)
        frame = Image.open(img_path0)
        frames.append(frame)
        img_mean, img_std = count_mean_std(os.path.join(img_dir_path, img_path0))
        # img_mean = [0.33067024, 0.5446649, 0.540241]
        # img_std = [0.36937192, 0.39847413, 0.32845193]
        # 预处理函数
        data_transform = transforms.Compose([
            # 将输入图像的尺寸变成224*224
            transforms.Resize((224, 224)),
            # 数据变成tensor类型，像素值归一化，调整维度[h,w,c]==>[c,h,w]
            transforms.ToTensor(),
            # 对每个通道的像素进行标准化，给出每个通道的均值和方差
            transforms.Normalize(mean=img_mean, std=img_std)
        ])
        img = data_transform(frame)
        # 给图像增加batch维度 [c,h,w]==>[b,c,h,w]
        img = torch.unsqueeze(img, dim=0)
        with torch.no_grad():
            # 前向传播
            outputs = model(img)
            # 只有一张图就挤压掉batch维度
            outputs = torch.squeeze(outputs)

            # 计算图片属于2个类别的概率
            predict = torch.softmax(outputs, dim=0)
            print(predict)
            # 得到类别索引
            predict_cla = torch.argmax(predict).numpy()
            print(predict_cla)
            predict_clas.append(predict_cla)

        # 获取最大预测类别概率
        predict_score = round(torch.max(predict).item(), 2)
        predict_scores.append(predict_score)
        # 获取预测类别的名称
        predict_name = class_names[predict_cla]
        predict_names.append(predict_name)
        if predict_name == negative:
            predict_y = 0
        else:
            predict_y = 1

        # 准备绘制roc曲线所需要的数据
        positive_pre = outputs[1]
        positive_pre = positive_pre.detach().numpy()
        positive_pre = positive_pre.tolist()
        pre_score.append(positive_pre)
        if label == negative:
            label_ture = 0
            ture_labels += [0]
        else:
            label_ture = 1
            ture_labels += [1]

        cnf_matrix[label_ture][predict_y] += 1

        if predict_name == label:
            acc += 1
            print("labels:{}->pre:{}  预测正确".format(label, predict_name))
        else:
            print("labels:{}->pre:{}  预测错误".format(label, predict_name))

print("一共校验了" + str(image_len) + "张图片，其中正确的有" + str(acc) + "张")
acc = acc / image_len
print("acc:" + str(acc))

"""
绘制roc曲线
"""
clr_1 = 'tab:green'
clr_2 = 'tab:green'
clr_3 = 'k'
fpr, tpr, thersholds = roc_curve(ture_labels, pre_score)
roc_auc1 = auc(fpr, tpr)
roc_auc = roc_auc1 * 100
plt.plot(fpr, tpr, label=' (auc = {0:.2f})'.format(roc_auc), c=clr_1, alpha=1)
plt.xlim([-0.05, 1.05])  # 设置x、y轴的上下限，以免和边缘重合，更好的观察图像的整体
plt.ylim([-0.05, 1.05])
plt.plot([0, 1], [0, 1], linestyle='--', label='chance', c=clr_3, alpha=.5)
plt.legend(loc='lower right', frameon=False)
plt.gca().spines['right'].set_visible(False)
plt.gca().spines['top'].set_visible(False)
plt.grid(color='gray', linestyle='--', linewidth=1, alpha=.3)
plt.text(0, 1, 'PATIENT-LEVEL ROC', color='gray', fontsize=12)
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')  # 可以使用中文，但需要导入一些库即字体
plt.title('ROC Curve')
plt.legend(loc="lower right")
plt.savefig("D:/学习/大创/data/训练数据集/model/photo/" + dir_path + "/model_ROC_" + str(nowTime) + ".jpg")
plt.show()

# 每次绘制9张图片，最后一组不够9的直接舍弃
# 计算一共有几组
# group_num = int(image_len / 9)
# for group in range(group_num):
#     frames_1 = frames[group * 9: (group + 1) * 9]
#     predict_name = predict_names[group * 9: (group + 1) * 9]
#     for i in range(9):
#         plt.subplot(3, 3, i + 1)
#         plt.imshow(frames_1[i])
#         plt.xticks([])  # 不显示x轴刻度
#         plt.yticks([])  # 不显示y轴刻度
#         plt.title(predict_name[i])
#     plt.tight_layout()  # 轻量化布局
#     plt.show()


"""
绘制混淆矩阵
"""
Confusion_matrix_path = "D:/学习/大创/data/训练数据集/model/photo/" + dir_path + "/Confusion matrix" + str(nowTime) + ".jpg"


# 绘制混淆矩阵
def plot_confusion_matrix(cm, classes, normalize=False, title='Confusion matrix', cmap=plt.cm.Blues,
                          path=Confusion_matrix_path):
    """
    - cm : 计算出的混淆矩阵的值
    - classes : 混淆矩阵中每一行每一列对应的列
    - normalize : True:显示百分比, False:显示个数
    """
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        #         print("显示百分比：")
        np.set_printoptions(formatter={'float': '{: 0.2f}'.format})
    #         print(cm)
    #     else:
    #         print('显示具体数字：')
    #         print(cm)
    plt.figure(dpi=320, figsize=(8, 8))
    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    plt.title(title, fontdict={'fontsize': 20})
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45, fontdict={'fontsize': 10})
    plt.yticks(tick_marks, classes, rotation=45, fontdict={'fontsize': 10})
    # matplotlib版本问题，如果不加下面这行代码，则绘制的混淆矩阵上下只能显示一半，有的版本的matplotlib不需要下面的代码，分别试一下即可
    plt.ylim(len(classes) - 0.5, -0.5)
    fmt = '.2f' if normalize else '.0f'
    # fmt = '.2f'
    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, format(cm[i, j], fmt), horizontalalignment="center",
                 color="red" if cm[i, j] > thresh else "red",
                 fontdict={'fontsize': 40})

    plt.tight_layout()
    plt.xlabel('Predicted label', fontdict={'fontsize': 20})
    plt.ylabel('True label', fontdict={'fontsize': 20})
    plt.subplots_adjust(left=0.12, right=0.95, bottom=0.2, top=0.9)
    # plt.show()
    plt.savefig(path)


# 第一种情况：显示百分比
# classes = ['cat', 'dog']
classes = ['negative', 'positive']
plot_confusion_matrix(cnf_matrix, classes=classes, normalize=False, title='Normalized confusion matrix')

# # 第二种情况：显示数字
# plot_confusion_matrix(cnf_matrix, classes=classes, normalize=False, title='Normalized confusion matrix')
