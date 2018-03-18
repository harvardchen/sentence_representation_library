#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/3/7 下午12:28
# @Author  : yizhen
# @Site    : 
# @File    : module.py
# @Software: PyCharm

import torch
from torch.nn.parameter import Parameter
import torch.nn as nn
from datautils import padding
import torch.nn.functional as F
from torch import optim
import numpy as np
import random

from torch.autograd import Variable
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

use_cuda = torch.cuda.is_available()


class Model(nn.Module):
    def __init__(self, args, input_size_, hidden_size_, output_size, vocal_size, embedding_size, dropout):
        super(Model, self).__init__()
        self.input_size = input_size_
        self.hidden_size = hidden_size_
        self.output_size = output_size
        self.vocal_size = vocal_size
        self.embedding_size = embedding_size
        self.args = args

        if args.encoder == 'lstm':
            self.encoder = LstmModel(self.args, self.input_size, self.hidden_size, self.output_size, self.vocal_size,
                                     self.embedding_size, dropout)
        elif args.encoder == 'bilstm':
            self.encoder = BilstmModel(self.args, self.input_size, self.hidden_size, self.output_size, self.vocal_size,
                                       self.embedding_size, dropout)
        elif args.encoder == 'cnn':
            self.encoder = CnnModel(self.args, self.input_size, self.hidden_size, self.output_size, self.vocal_size,
                                    self.embedding_size, dropout)
        elif args.encoder == 'sum':
            self.encoder = SumModel(self.vocal_size, self.embedding_size, self.output_size)

    def forward(self, input_x, input_y):
        """
         intput_x: b_s instances， 没有进行padding和Variable
        :param input_x:
        :param input_y:
        :return:
        """
        return self.encoder.forward(input_x, input_y)  # interface， implementated by every people


class LstmModel(nn.Module):
    def __init__(self, args, input_size_, hidden_size_, output_size, vocal_size, embedding_size, dropout):
        super(LstmModel, self).__init__()

        self.input_size = input_size_
        self.embedding_size = embedding_size
        self.hidden_size = hidden_size_
        self.output_size = output_size
        self.vocal_size = vocal_size
        self.seed = args.seed
        torch.manual_seed(self.seed)  # fixed the seed
        random.seed(self.seed)
        self.linear = nn.Linear(self.hidden_size, self.output_size)
        self.embedding = nn.Embedding(self.vocal_size, self.embedding_size)
        self.NLLoss = nn.NLLLoss()
        self.dropout = nn.Dropout(dropout)
        self.softmax = nn.LogSoftmax()
        self.lstm = nn.LSTM(input_size=self.input_size,
                            hidden_size=self.hidden_size,
                            batch_first=True,
                            dropout=dropout)

        self.w_i_in, self.w_i_on = self.lstm.all_weights[0][0].size()
        self.w_h_in, self.w_h_on = self.lstm.all_weights[0][1].size()
        self.lstm.all_weights[0][0] = Parameter(torch.randn(self.w_i_in, self.w_i_on)) * np.sqrt(2. / self.w_i_on)
        self.lstm.all_weights[0][1] = Parameter(torch.randn(self.w_h_in, self.w_h_on)) * np.sqrt(2. / self.w_h_on)

    def forward(self, input_x, input_y):
        """
        intput_x: b_s instances， 没有进行padding和Variable
        :param input:
        :return:
        """
        # input = input_x.squeeze(1)

        #
        input_x, input_y, sentence_lens = padding(input_x, input_y)
        max_len = len(input_x[0])

        if use_cuda:
            input_x = Variable(torch.LongTensor(input_x)).cuda()
            input_y = Variable(torch.LongTensor(input_y)).cuda()
        else:
            input_x = Variable(torch.LongTensor(input_x))
            input_y = Variable(torch.LongTensor(input_y))

        embed_input_x = self.embedding(input)  # embed_intput_x: (b_s, m_l, em_s)
        embed_input_x = self.dropout(embed_input_x)

        embed_input_x_packed = pack_padded_sequence(embed_input_x, sentence_lens, batch_first=True)
        encoder_outputs_packed, (h_last, c_last) = self.lstm(embed_input_x_packed)
        encoder_outputs, _ = pad_packed_sequence(encoder_outputs_packed, batch_first=True)

        predict = self.linear(h_last)  # predict: [1, b_s, o_s]
        predict = self.softmax(predict.squeeze(0))  # predict.squeeze(0) [b_s, o_s]

        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class BilstmModel(nn.Module):
    def __init__(self, args, input_size_, hidden_size_, output_size, vocal_size, embedding_size, dropout):
        super(BilstmModel, self).__init__()

        self.input_size = input_size_
        self.embedding_size = embedding_size
        self.hidden_size = hidden_size_
        self.output_size = output_size
        self.vocal_size = vocal_size
        self.seed = args.seed
        self.linear = nn.Linear(self.hidden_size * 2, self.output_size)
        self.embedding = nn.Embedding(self.vocal_size, self.embedding_size)
        self.NLLoss = nn.NLLLoss()
        self.dropout = nn.Dropout(dropout)
        self.softmax = nn.LogSoftmax()
        self.lstm = nn.LSTM(input_size=self.input_size,
                            hidden_size=self.hidden_size,
                            batch_first=True,
                            dropout=dropout,
                            bidirectional=True)

    def forward(self, input_x, input_y):
        """
        intput_x: b_s instances， 没有进行padding和Variable
        :param input:
        :return:
        """
        # input = input_x.squeeze(1)

        #
        input_x, input_y, sentence_lens = padding(input_x, input_y)
        max_len = len(input_x[0])

        if use_cuda:
            input_x = Variable(torch.LongTensor(input_x)).cuda()
            input_y = Variable(torch.LongTensor(input_y)).cuda()
        else:
            input_x = Variable(torch.LongTensor(input_x))
            input_y = Variable(torch.LongTensor(input_y))

        embed_input_x = self.embedding(input_x)  # embed_intput_x: (b_s, m_l, em_s)
        embed_input_x = self.dropout(embed_input_x)

        encoder_outputs, (h_last, c_last) = self.lstm(embed_input_x)
        h_last = torch.cat((h_last[0], h_last[1]), 1)

        predict = self.linear(h_last)  # predict: [1, b_s, o_s]
        predict = self.softmax(predict.squeeze(0))  # predict.squeeze(0) [b_s, o_s]

        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class CnnModel(nn.Module):

    def __init__(self, args, input_size_, hidden_size_, output_size, vocal_size, embedding_size, dropout):
        super(CnnModel, self).__init__()

        self.input_size = input_size_
        self.embedding_size = embedding_size
        self.hidden_size = hidden_size_
        self.output_size = output_size
        self.vocal_size = vocal_size
        self.seed = args.seed
        self.embedding = nn.Embedding(self.vocal_size, self.embedding_size)
        self.NLLoss = nn.NLLLoss()
        self.dropout = nn.Dropout(dropout)
        self.softmax = nn.LogSoftmax()

        self.l2 = args.l2
        self.kernel_size = [int(size) for size in args.kernel_size.split("*")]
        self.kernel_num = [int(num) for num in args.kernel_num.split("*")]
        nums = 0
        for n in self.kernel_num:
            nums += n
        self.linear = nn.Linear(nums, self.output_size)
        self.convs = nn.ModuleList(
            [nn.Conv2d(1, num, (size, self.embedding_size)) for (size, num) in zip(self.kernel_size, self.kernel_num)])

    def forward(self, input_x, input_y):
        input_x, input_y, sentence_lens = padding(input_x, input_y)
        max_len = len(input_x[0])
        self.poolings = nn.ModuleList([nn.MaxPool1d(max_len - size + 1, 1) for size in
                                       self.kernel_size])  # the output of each pooling layer is a number

        if use_cuda:
            input_x = Variable(torch.LongTensor(input_x)).cuda()
            input_y = Variable(torch.LongTensor(input_y)).cuda()
        else:
            input_x = Variable(torch.LongTensor(input_x))
            input_y = Variable(torch.LongTensor(input_y))

        embed_input_x = self.embedding(input)  # embed_intput_x: (b_s, m_l, em_s)
        embed_input_x = self.dropout(embed_input_x)
        embed_input_x = embed_input_x.view(embed_input_x.size(0), 1, -1, embed_input_x.size(2))

        parts = []  # example:[3,4,5] [100,100,100] the dims of data though pooling layer is 100 + 100 + 100 = 300
        for (conv, pooling) in zip(self.convs, self.poolings):
            parts.append(pooling(conv(embed_input_x).squeeze()).view(input_x.size(0), -1))
        x = F.relu(torch.cat(parts, 1))

        # make sure the l2 norm of w less than l2
        w = torch.mul(self.linear.weight, self.linear.weight).sum().data[0]
        if w > self.l2 * self.l2:
            x = torch.mul(x.weight, math.sqrt(self.l2 * self.l2 * 1.0 / w))

        predict = self.linear(x)  # predict: [1, b_s, o_s]
        predict = self.softmax(predict.squeeze(0))  # predict.squeeze(0) [b_s, o_s]

        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class SumModel(nn.Module):
    def __init__(self, vocal_size, embedding_size, output_size):
        super(SumModel, self).__init__()
        self.vocal_size = vocal_size
        self.embedding_size = embedding_size
        self.embedding = nn.Embedding(self.vocal_size, self.embedding_size)
        self.output_size = output_size
        self.linear = nn.Linear(self.embedding_size, self.output_size)
        self.softmax = nn.LogSoftmax()
        self.NLLoss = nn.NLLLoss()

    def forward(self, input_x, input_y):

        input_x, input_y, sentence_lens = padding(input_x, input_y)  # padding

        if use_cuda:
            input_x = Variable(torch.LongTensor(input_x)).cuda()
            input_y = Variable(torch.LongTensor(input_y)).cuda()
        else:
            input_x = Variable(torch.LongTensor(input_x))
            input_y = Variable(torch.LongTensor(input_y))

        embed_input_x = self.embedding(input_x)  # 取出embedding

        encoder_outputs = torch.zeros(len(input_y), self.embedding_size)  # 存放加和平均的句子表示

        if use_cuda:
            encoder_outputs = Variable(encoder_outputs).cuda()
        else:
            encoder_outputs = Variable(encoder_outputs)

        for index, batch in enumerate(embed_input_x):
            true_batch = batch[0:sentence_lens[index]]  # 根据每一个句子的实际长度取出实际batch
            encoder_outputs[index] = torch.mean(true_batch, 0)  # 平均

        predict = self.linear(encoder_outputs)
        predict = self.softmax(predict)
        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc
