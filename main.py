#!/usr/bin/env python3

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import os
import sys
import math
import time
import shutil
import numpy as np
from dataloader import get_dataloaders
from args import arg_parser
from adaptive_inference import dynamic_evaluate
import models
from op_counter import measure_model
import torch

sm = torch.nn.Softmax(dim=1)

args = arg_parser.parse_args()

if args.gpu:
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

args.grFactor = list(map(int, args.grFactor.split('-')))
args.bnFactor = list(map(int, args.bnFactor.split('-')))
args.nScales = len(args.grFactor)

if args.use_valid:
    args.splits = ['train', 'val', 'test']
else:
    args.splits = ['train', 'val']

if args.data == 'cifar10':
    args.num_classes = 10
elif args.data == 'cifar100':
    args.num_classes = 100
else:
    args.num_classes = 1000

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim

torch.manual_seed(args.seed)

def main():

    global args
    best_prec1, best_epoch = 0.0, 0

    if not os.path.exists(args.save):
        os.makedirs(args.save)

    if args.data.startswith('cifar'):
        IM_SIZE = 32
    else:
        IM_SIZE = 224

    model = getattr(models, args.arch)(args)
    n_flops, n_params = measure_model(model, IM_SIZE, IM_SIZE)    
    torch.save(n_flops, os.path.join(args.save, 'flops.pth'))
    del(model)
        
        
    model = getattr(models, args.arch)(args)

    if args.arch.startswith('alexnet') or args.arch.startswith('vgg'):
        model.features = torch.nn.DataParallel(model.features)
        model.cuda()
    else:
        model = torch.nn.DataParallel(model).cuda()

    criterion = nn.CrossEntropyLoss().cuda()

    optimizer = torch.optim.SGD(model.parameters(), args.lr,
                                momentum=args.momentum,
                                weight_decay=args.weight_decay)

    if args.resume:
        checkpoint = load_checkpoint(args)
        if checkpoint is not None:
            args.start_epoch = checkpoint['epoch'] + 1
            best_prec1 = checkpoint['best_prec1']
            model.load_state_dict(checkpoint['state_dict'])
            optimizer.load_state_dict(checkpoint['optimizer'])

    cudnn.benchmark = True

    train_loader, val_loader, test_loader = get_dataloaders(args)

    if args.evalmode is not None:
        state_dict = torch.load(args.evaluate_from)['state_dict']
        model.load_state_dict(state_dict)

        if args.evalmode == 'anytime':
            validate(test_loader, model, criterion)
        else:
            dynamic_evaluate(model, test_loader, val_loader, args)
        return

    #scores = ['epoch\tlr\ttrain_loss\tval_loss\ttrain_prec1\tval_prec1\ttrain_prec5\tval_prec5']
    scores = ['epoch\tlr\ttrain_loss\tval_loss\tval1_prec1\tval2_prec1\tval3_prec1\tval4_prec1\tval5_prec1']

    for epoch in range(args.start_epoch, args.epochs):

        train_loss, train_prec1, train_prec5, lr = train(train_loader, model, criterion, optimizer, epoch)

        conf, val_loss, valexits_prec1, val_prec1, val_prec5 = validate(val_loader, model, criterion)

        #scores.append(('{}\t{:.3f}' + '\t{:.4f}' * 6)
        #              .format(epoch, lr, train_loss, val_loss,
        #                      train_prec1, val_prec1, train_prec5, val_prec5))


        scores.append(('\t{:.4f}' * 9).format(epoch, lr, train_loss, val_loss, valexits_prec1[0], valexits_prec1[1], valexits_prec1[2], valexits_prec1[3], valexits_prec1[4])) 

        is_best = val_prec1 > best_prec1
        if is_best:
            best_prec1 = val_prec1
            best_epoch = epoch
            print('Best var_prec1 {}'.format(best_prec1))

        model_filename = 'checkpoint_%03d.pth.tar' % epoch
        save_checkpoint({
            'epoch': epoch,
            'arch': args.arch,
            'state_dict': model.state_dict(),
            'best_prec1': best_prec1,
            'optimizer': optimizer.state_dict(),
        }, args, is_best, model_filename, scores)

        print("Epoch :",epoch," of ",args.epochs,"\n")

    print('Best val_prec1: {:.4f} at epoch {}'.format(best_prec1, best_epoch))

    ### Test the final model

    print('********** Final prediction results **********')
    validate(test_loader, model, criterion)

    #print(conf,"conf...............\n")
    save_final_probabilities(conf)

    return 

def train(train_loader, model, criterion, optimizer, epoch):
    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    top1, top5 = [], []
    for i in range(args.nBlocks):
        top1.append(AverageMeter())
        top5.append(AverageMeter())

    # switch to train mode
    model.train()

    end = time.time()

    running_lr = None
    for i, (input, target) in enumerate(train_loader):
        lr = adjust_learning_rate(optimizer, epoch, args, batch=i,
                                  nBatch=len(train_loader), method=args.lr_type)

        if running_lr is None:
            running_lr = lr

        data_time.update(time.time() - end)

        target = target.cuda(async=True)
        input_var = torch.autograd.Variable(input)
        target_var = torch.autograd.Variable(target)

        output = model(input_var)
        if not isinstance(output, list):
            output = [output]

        loss = 0.0
        for j in range(len(output)):
            loss += criterion(output[j], target_var)

        losses.update(loss.item(), input.size(0))

        for exit in range(len(output)):
            output[exit] = sm(output[exit])

        for j in range(len(output)):
            prec1, prec5, conf_1_c, conf_1_w, conf_1_correct_count, conf_c_batch, class_c_batch, conf_w_batch, class_w_batch = accuracy(output[j].data, target, topk=(1, 5))
            top1[j].update(prec1.item(), input.size(0))
            top5[j].update(prec5.item(), input.size(0))

        # compute gradient and do SGD step
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()
        '''
        if i % args.print_freq == 0:
            print('Epoch: [{0}][{1}/{2}]\t'
                  'Time {batch_time.avg:.3f}\t'
                  'Data {data_time.avg:.3f}\t'
                  'Loss {loss.val:.4f}\t'
                  'Acc@1 {top1.val:.4f}\t'
                  'Acc@5 {top5.val:.4f}'.format(
                    epoch, i + 1, len(train_loader),
                    batch_time=batch_time, data_time=data_time,
                    loss=losses, top1=top1[-1], top5=top5[-1]))
        '''
    return losses.avg, top1[-1].avg, top5[-1].avg, running_lr

def validate(val_loader, model, criterion):
    batch_time = AverageMeter()
    losses = AverageMeter()
    data_time = AverageMeter()
    top1, top5 = [], []
    conf_1_c_sum = [0.0] * args.nBlocks
    conf_1_w_sum = [0.0] * args.nBlocks
    conf_1_c_count = [0] * args.nBlocks
    conf_1_w_count = [0] * args.nBlocks
    conf_1_c_prob = [[] for _ in range(args.nBlocks)]
    conf_1_w_prob = [[] for _ in range(args.nBlocks)]
    conf_1_c_class = [[] for _ in range(args.nBlocks)]
    conf_1_w_class = [[] for _ in range(args.nBlocks)]

    for i in range(args.nBlocks):
        top1.append(AverageMeter())
        top5.append(AverageMeter())

    model.eval()

    end = time.time()
    with torch.no_grad():
        for i, (input, target) in enumerate(val_loader):
            target = target.cuda(async=True)
            input = input.cuda()

            input_var = torch.autograd.Variable(input)
            target_var = torch.autograd.Variable(target)

            data_time.update(time.time() - end)

            output = model(input_var)
            if not isinstance(output, list):
                output = [output]

            loss = 0.0
            for j in range(len(output)):
                loss += criterion(output[j], target_var)

            losses.update(loss.item(), input.size(0))

            for exit in range(len(output)):
                output[exit] = sm(output[exit]) 


            for j in range(len(output)):
                prec1, prec5, conf_1_c, conf_1_w, conf_1_correct_count, conf_c_batch, class_c_batch, conf_w_batch, class_w_batch = accuracy(output[j].data, target, topk=(1, 5))
                top1[j].update(prec1.item(), input.size(0))
                top5[j].update(prec5.item(), input.size(0))
                conf_1_c_sum[j] = (conf_1_c_sum[j] * conf_1_c_count[j] + conf_1_c)/(conf_1_c_count[j] + conf_1_correct_count)
                conf_1_w_sum[j] = (conf_1_w_sum[j] * conf_1_w_count[j] + conf_1_w)/(conf_1_w_count[j] + 256 - conf_1_correct_count)
                conf_1_c_count[j] = conf_1_c_count[j] + conf_1_correct_count
                conf_1_w_count[j] = conf_1_w_count[j] + 256 - conf_1_correct_count
                conf_1_c_prob[j] = conf_1_c_prob[j] + conf_c_batch.tolist()
                conf_1_w_prob[j] = conf_1_w_prob[j] + conf_w_batch.tolist()
                conf_1_c_class[j] = conf_1_c_class[j] + class_c_batch
                conf_1_w_class[j] = conf_1_w_class[j] + class_w_batch

            # measure elapsed time
            batch_time.update(time.time() - end)
            end = time.time()
            '''
            if i % args.print_freq == 0:
                print('Epoch: [{0}/{1}]\t'
                      'Time {batch_time.avg:.3f}\t'
                      'Data {data_time.avg:.3f}\t'
                      'Loss {loss.val:.4f}\t'
                      'Acc@1 {top1.val:.4f}\t'
                      'Acc@5 {top5.val:.4f}'.format(
                        i + 1, len(val_loader),
                        batch_time=batch_time, data_time=data_time,
                        loss=losses, top1=top1[-1], top5=top5[-1]))
            '''
    for j in range(args.nBlocks):
        print(' exit {} prec@1 {top1.avg:.3f} '.format(j,top1=top1[j]))
        print(' exit {} prec@1 conf correct {correct:.3f} prec@1 conf wrong {wrong:.3f}'.format(j,correct=conf_1_c_sum[j], wrong=conf_1_w_sum[j]))
    # print(' * prec@1 {top1.avg:.3f} prec@5 {top5.avg:.3f}'.format(top1=top1[-1], top5=top5[-1]))
    top1_exits = [top1[0].avg,top1[1].avg,top1[2].avg,top1[3].avg,top1[4].avg]
    conf = [conf_1_c_prob, conf_1_w_prob, conf_1_c_class, conf_1_w_class]
    return conf, losses.avg, top1_exits, top1[-1].avg, top5[-1].avg

def save_final_probabilities(conf):
    result_filename_c = os.path.join(args.save, 'confidence_c.tsv')
    result_filename_w = os.path.join(args.save, 'confidence_w.tsv')

    confidence_c = ['\tExit\tConfidence\tClass']
    confidence_w = ['\tExit\tConfidence\tClass']

    for exit in range(args.nBlocks):
        for prob in range(len(conf[0][exit])):
            if conf[0][exit][prob][0] != 0.00:
                confidence_c.append(('\t{}\t{:.4f}\t{}').format(exit,conf[0][exit][prob][0],conf[2][exit][prob]))

    for exit in range(args.nBlocks):
        for prob in range(len(conf[1][exit])):
            if conf[1][exit][prob][0] != 0.00:
                confidence_w.append(('\t{}\t{:.4f}\t{}').format(exit,conf[1][exit][prob][0],conf[3][exit][prob]))


    with open(result_filename_c, 'w') as f:
        print('\n'.join(confidence_c), file=f)

    with open(result_filename_w, 'w') as f:
        print('\n'.join(confidence_w), file=f)

def save_checkpoint(state, args, is_best, filename, result):
    print(args)
    result_filename = os.path.join(args.save, 'scores.tsv')
    model_dir = os.path.join(args.save, 'save_models')
    latest_filename = os.path.join(model_dir, 'latest.txt')
    model_filename = os.path.join(model_dir, filename)
    best_filename = os.path.join(model_dir, 'model_best.pth.tar')
    os.makedirs(args.save, exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)
    print("=> saving checkpoint '{}'".format(model_filename))

    torch.save(state, model_filename)

    with open(result_filename, 'w') as f:
        print('\n'.join(result), file=f)

    with open(latest_filename, 'w') as fout:
        fout.write(model_filename)
    if is_best:
        shutil.copyfile(model_filename, best_filename)

    print("=> saved checkpoint '{}'".format(model_filename))
    return

def load_checkpoint(args):
    model_dir = os.path.join(args.save, 'save_models')
    latest_filename = os.path.join(model_dir, 'latest.txt')
    if os.path.exists(latest_filename):
        with open(latest_filename, 'r') as fin:
            model_filename = fin.readlines()[0].strip()
    else:
        return None
    print("=> loading checkpoint '{}'".format(model_filename))
    state = torch.load(model_filename)
    print("=> loaded checkpoint '{}'".format(model_filename))
    return state

class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

def accuracy(output, target, topk=(1,)):
    """Computes the precor@k for the specified values of k"""
    maxk = max(topk)
    batch_size = target.size(0)

    conf, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    conf = conf.t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))
    conf_c = conf * correct
    class_c = correct[:1] * target
    conf_w = conf * (~correct) 
    class_w = (~correct[:1]) * target
    res = []
    for k in topk:
        correct_k = correct[:k].view(-1).float().sum(0)
        res.append(correct_k.mul_(100.0 / batch_size))
    correct_count = torch.sum((correct[:1] == True).int())
    conf_1_c = conf_c[:1].view(-1).float().sum(0)
    conf_1_w = conf_w[:1].view(-1).float().sum(0)
    res.append(conf_1_c)
    res.append(conf_1_w)
    res.append(correct_count)
    res.append(conf_c[:1].t())
    res.append(class_c.tolist()[0])
    res.append(conf_w[:1].t())
    res.append(class_w.tolist()[0])
    return res

def adjust_learning_rate(optimizer, epoch, args, batch=None,
                         nBatch=None, method='multistep'):
    if method == 'cosine':
        T_total = args.epochs * nBatch
        T_cur = (epoch % args.epochs) * nBatch + batch
        lr = 0.5 * args.lr * (1 + math.cos(math.pi * T_cur / T_total))
    elif method == 'multistep':
        if args.data.startswith('cifar'):
            lr, decay_rate = args.lr, 0.1
            if epoch >= args.epochs * 0.75:
                lr *= decay_rate ** 2
            elif epoch >= args.epochs * 0.5:
                lr *= decay_rate
        else:
            lr = args.lr * (0.1 ** (epoch // 30))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
    return lr

if __name__ == '__main__':
    main()
