from collections import Counter

import numpy as np
import pandas as pd
import torch.nn as nn
import torch.nn.functional as F
from sklearn.manifold import TSNE
from sklearn.preprocessing import OneHotEncoder
from viapi.fileutils import FileUtils
from win32 import win32api, win32gui

import jieba
import torch
from torch import nn

class lstm_model(nn.Module):
    def __init__(self, vocab, hidden_size, num_layers, dropout=0.5):
        super(lstm_model, self).__init__()
        self.vocab = vocab  # 字符数据集
        # 索引，字符
        self.int_char = {i: char for i, char in enumerate(vocab)}
        self.char_int = {char: i for i, char in self.int_char.items()}
        # 对字符进行one-hot encoding
        self.encoder = OneHotEncoder(sparse=True).fit(vocab.reshape(-1, 1))

        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # lstm层
        self.lstm = nn.LSTM(len(vocab), hidden_size,
                            num_layers, batch_first=True, dropout=dropout)

        # 全连接层
        self.linear = nn.Linear(hidden_size, len(vocab))

    def forward(self, sequence, hs=None):
        # lstm的输出格式（batch_size, sequence_length, hidden_size）
        out, hs = self.lstm(sequence, hs)
        # 这里需要将out转换为linear的输入格式，即（batch_size * sequence_length, hidden_size）
        out = out.reshape(-1, self.hidden_size)
        # linear的输出格式，(batch_size * sequence_length, vocab_size)
        output = self.linear(out)
        return output, hs

    def onehot_encode(self, data):  # 对数据进行编码
        return self.encoder.transform(data)

    def onehot_decode(self, data):  # 对数据进行解码
        return self.encoder.inverse_transform(data)

    def label_encode(self, data):  # 对标签进行编码
        return np.array([self.char_int[ch] for ch in data])

    def label_decode(self, data):  # 对标签进行解码
        return np.array([self.int_char[ch] for ch in data])

def predict(model, char, top_k=None, hidden_size=None):
    model.to(device)
    model.eval()  # 固定参数
    with torch.no_grad():
        char = np.array([char])  # 输入一个字符，预测下一个字是什么，先转成numpy
        char = char.reshape(-1, 1)  # 变成二维才符合编码规范
        char_encoding = model.onehot_encode(char).A  # 对char进行编码，取成numpy比较方便reshape
        char_encoding = char_encoding.reshape(1, 1, -1)  # char_encoding.shape为(1, 1, 43)变成三维才符合模型输入格式
        char_tensor = torch.tensor(char_encoding, dtype=torch.float32)  # 转成tensor
        char_tensor = char_tensor.to(device)

        out, hidden_size = model(char_tensor, hidden_size)  # 放入模型进行预测，out为结果

        probs = F.softmax(out, dim=1).squeeze()  # 计算预测值,即所有字符的概率

        if top_k is None:  # 选择概率最大的top_k个
            indices = np.arange(vocab_size)
        else:
            probs, indices = probs.topk(top_k)
            indices = indices.cpu().numpy()
        probs = probs.cpu().numpy()

        char_index = np.random.choice(indices, p=probs/probs.sum())  # 随机选择一个字符索引作为预测值
        char = model.int_char[char_index]  # 通过索引找出预测字符

    return char, hidden_size

def sample(model, length, top_k, sentence):
    hidden_size = None
    new_sentence = [char for char in sentence]
    for i in range(length):
        next_char, hidden_size = predict(model, new_sentence[-1], top_k=top_k, hidden_size=hidden_size)
        new_sentence.append(next_char)
    return "".join(new_sentence)
def main(txt_path,model_path):
    global batch_size,seq_len,epochs,lr,vocab_size,trainset,validset,device
    hidden_size = 100
    num_layers = 2
    batch_size = 256
    seq_len = 100
    epochs = 300
    lr = 0.01
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    text = pd.read_csv(txt_path, sep="。", header=None)
    text = text[0]
    text = list(text)
    text = "。".join(text)
    vocab = np.array(sorted(set(text)))  # 建立字典
    vocab_size = len(vocab)

    val_len = int(np.floor(0.2 * len(text)))  # 划分训练测试集
    trainset = np.array(list(text[:-val_len]))
    validset = np.array(list(text[-val_len:]))

    model = lstm_model(vocab, hidden_size, num_layers)  # 模型实例化
    try:
        if device.type == 'cpu':# 调用保存的模型
            model.load_state_dict(torch.load(model_path, map_location='cpu'))
        else:
            model.load_state_dict(torch.load(model_path))  
    except Exception as e:
        print('>>> No Model Loaded\n',e)
    return model
    # while True:
    #     out_word = input('请输入起始词:')
    #     new_text = sample(model, 50, 3,out_word)  # 预测模型，生成150个字符,预测时选择概率最大的前2个
    #     new_text = new_text.split('.')[0]
    #     print(new_text)  # 输出预测文本
