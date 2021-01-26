#from __future__ import print_function

import argparse
#import json
import logging
import os
#import sys

import numpy as np
import pandas as pd
import torch
from torch import nn
#import torch.utils.data
#import torch.utils.data.distributed
from torch.utils.data import DataLoader, RandomSampler
#from transformers import BertTokenizer, get_linear_schedule_with_warmup
from transformers import AutoTokenizer, get_linear_schedule_with_warmup
import torch_optimizer as optim

# Network definition
from clf_model import TextClassifier
from data_prep import MedborgerDataset
 
## SageMaker Distributed code.
#from smdistributed.dataparallel.torch.parallel.distributed import DistributedDataParallel as DDP
#import smdistributed.dataparallel.torch.distributed as dist

#dist.init_process_group()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))

MAX_LEN = 512  # this is the max length of the sequence
model_checkpoint = 'Maltehb/-l-ctra-danish-electra-small-uncased'
tokenizer = AutoTokenizer.from_pretrained(model_checkpoint, use_fast=True)

def _get_train_data_loader(batch_size, training_dir):
    dataset = pd.read_csv(os.path.join(training_dir, "train_df.csv"), sep="\t")
    train_data = MedborgerDataset(
        sentence=dataset.sentence.to_numpy(),
        label=dataset.label.to_numpy(),
        tokenizer=tokenizer,
        max_len=MAX_LEN
    )
    train_sampler = RandomSampler(train_data)

    train_dataloader = DataLoader(train_data, batch_size=batch_size, shuffle=False, sampler=train_sampler)
    return train_dataloader

def _get_test_data_loader(batch_size, training_dir):
    dataset = pd.read_csv(os.path.join(training_dir, "test_df.csv"), sep="\t")
    test_data = MedborgerDataset(
        sentence=dataset.sentence.to_numpy(),
        label=dataset.label.to_numpy(),
        tokenizer=tokenizer,
        max_len=MAX_LEN
  )
    test_sampler = RandomSampler(test_data)
    test_dataloader = DataLoader(test_data, sampler=test_sampler, batch_size=batch_size)
    return test_dataloader


def freeze(model, frozen_layers):
    for param in model.pretrained_model.electra.parameters():
        param.requires_grad = False




def train(args):
    use_cuda = args.num_gpus > 0
    device = torch.device("cuda" if use_cuda else "cpu")
    
    #world_size = dist.get_world_size()
    #rank = dist.get_rank()
    #local_rank = dist.get_local_rank()
    
    # set the seed for generating random numbers
    torch.manual_seed(args.seed)
    if use_cuda:
        torch.cuda.manual_seed(args.seed)

    train_loader = _get_train_data_loader(args.batch_size, args.data_dir)
    
    test_loader = _get_test_data_loader(args.test_batch_size, args.data_dir)
    #rank = 0
    
    #if rank == 0:
    #    test_loader = _get_test_data_loader(args.test_batch_size, args.test)
    #    print("Max length of sequence: ", MAX_LEN)
    #    print("Freezing {} layers".format(args.frozen_layers))
    #    print("Model used: ", PRE_TRAINED_MODEL_NAME)

    print(
        "Processes {}/{} ({:.0f}%) of train data".format(
            len(train_loader.sampler),
            len(train_loader.dataset),
            100.0 * len(train_loader.sampler) / len(train_loader.dataset),
        )
    )

    model = TextClassifier(
        args.num_labels  # The number of output labels.
    )

    freeze(model, args.frozen_layers)


    #model = DDP(model.to(device), broadcast_buffers=False)
    #torch.cuda.set_device(local_rank)
    #model.cuda(local_rank)
    
    optimizer = optim.Lamb(
            model.parameters(), 
            lr = args.lr, 
            betas=(0.9, 0.999), 
            eps=args.epsilon, 
            weight_decay=args.weight_decay)
    
    total_steps = len(train_loader.dataset)
    
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=0,
        num_training_steps=total_steps)
    
    loss_fn = nn.CrossEntropyLoss().to(device)



    for epoch in range(1, args.epochs + 1):
        model.train()
        for step, batch in enumerate(train_loader):
            b_input_ids = batch['input_ids'].to(device)
            b_input_mask = batch['attention_mask'].to(device)
            b_labels = batch['label'].to(device)

            #outputs = model(b_input_ids,attention_mask=b_input_mask)
            outputs = model(b_input_ids, attention_mask=b_input_mask, labels=b_labels)

            loss = outputs.loss
            #loss = loss_fn(outputs, b_labels)

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            # modified based on their gradients, the learning rate, etc.
            optimizer.step()
            optimizer.zero_grad()
            
            # if step % args.log_interval == 0 and rank == 0:
            #     logger.info(
            #         "Collecting data from Master Node: \n Train Epoch: {} [{}/{} ({:.0f}%)] Training Loss: {:.6f}".format(
            #             epoch,
            #             step * len(batch['input_ids'])*world_size,
            #             len(train_loader.dataset),
            #             100.0 * step / len(train_loader),
            #             loss.item(),
            #         )
            #     )
            if args.verbose:
                print('Batch', step)
        scheduler.step()


#if __name__ == "__main__":
parser = argparse.ArgumentParser()

# Data and model checkpoints directories
parser.add_argument(
    "--num_labels", type=int, default=2, metavar="N", help="Number of labels."
)

parser.add_argument(
    "--batch-size", type=int, default=16, metavar="N", help="input batch size for training (default: 16)"
)
parser.add_argument(
    "--test-batch-size", type=int, default=8, metavar="N", help="input batch size for testing (default: 8)"
)
parser.add_argument("--epochs", type=int, default=2, metavar="N", help="number of epochs to train (default: 2)")
parser.add_argument("--lr", type=float, default=0.3e-5, metavar="LR", help="learning rate (default: 0.3e-5)")
parser.add_argument("--weight_decay", type=float, default=0.01, metavar="M", help="weight_decay (default: 0.01)")
parser.add_argument("--seed", type=int, default=43, metavar="S", help="random seed (default: 43)")
parser.add_argument("--epsilon", type=int, default=1e-8, metavar="EP", help="random seed (default: 1e-8)")
parser.add_argument("--frozen_layers", type=int, default=10, metavar="NL", help="number of frozen layers(default: 10)")
#parser.add_argument('--verbose', action='store_true', default=False,help='For displaying SMDataParallel-specific logs')
#parser.add_argument(
#    "--log-interval",
#    type=int,
#    default=10,
#    metavar="N",
#    help="how many batches to wait before logging training status",
#)

# Container environment
#parser.add_argument("--hosts", type=list, default=json.loads(os.environ["SM_HOSTS"]))
#parser.add_argument("--current-host", type=str, default=os.environ["SM_CURRENT_HOST"])
#parser.add_argument("--model-dir", type=str, default=os.environ["SM_MODEL_DIR"])
#parser.add_argument("--data-dir", type=str, default=os.environ["SM_CHANNEL_TRAINING"])
parser.add_argument("--data-dir", type=str, default='.')

#parser.add_argument("--test", type=str, default=os.environ["SM_CHANNEL_TESTING"])
#parser.add_argument("--num-gpus", type=int, default=os.environ["SM_NUM_GPUS"])
parser.add_argument("--num-gpus", type=int, default=False)

    #train(parser.parse_args())




args = parser.parse_args()


use_cuda = args.num_gpus > 0
device = torch.device("cuda" if use_cuda else "cpu")

#world_size = dist.get_world_size()
#rank = dist.get_rank()
#local_rank = dist.get_local_rank()

# set the seed for generating random numbers
torch.manual_seed(args.seed)
if use_cuda:
    torch.cuda.manual_seed(args.seed)

train_loader = _get_train_data_loader(args.batch_size, args.data_dir)

test_loader = _get_test_data_loader(args.test_batch_size, args.data_dir)
#rank = 0

#if rank == 0:
#    test_loader = _get_test_data_loader(args.test_batch_size, args.test)
#    print("Max length of sequence: ", MAX_LEN)
#    print("Freezing {} layers".format(args.frozen_layers))
#    print("Model used: ", PRE_TRAINED_MODEL_NAME)

print(
    "Processes {}/{} ({:.0f}%) of train data".format(
        len(train_loader.sampler),
        len(train_loader.dataset),
        100.0 * len(train_loader.sampler) / len(train_loader.dataset),
    )
)

model = TextClassifier(
    args.num_labels  # The number of output labels.
)

freeze(model, args.frozen_layers)


#model = DDP(model.to(device), broadcast_buffers=False)
#torch.cuda.set_device(local_rank)
#model.cuda(local_rank)

optimizer = optim.Lamb(
        model.parameters(), 
        lr = args.lr, 
        betas=(0.9, 0.999), 
        eps=args.epsilon, 
        weight_decay=args.weight_decay)

total_steps = len(train_loader.dataset)

scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=0,
    num_training_steps=total_steps)

loss_fn = nn.CrossEntropyLoss().to(device)



def test(model, test_loader, device):
    model.eval()
    losses = []
    correct_predictions = 0
    loss_fn = nn.CrossEntropyLoss().to(device)
    tmp_eval_accuracy, eval_accuracy = 0, 0
    
    with torch.no_grad():
        for batch in test_loader:
            b_input_ids = batch['input_ids'].to(device)
            b_input_mask = batch['attention_mask'].to(device)
            b_labels = batch['label'].to(device)

            outputs = model(b_input_ids,attention_mask=b_input_mask,labels=b_labels)
            _, preds = torch.max(outputs.logits, dim=1)
            loss = loss_fn(outputs.logits, b_labels)
            correct_predictions += torch.sum(preds == b_labels)
            losses.append(loss.item())
            
    print('\nTest set: Validation loss: {:.4f}, Validation Accuracy: {:.0f}%\n'.format(
        np.mean(losses),
        100. * correct_predictions.double() / len(test_loader.dataset)))



for epoch in range(1, args.epochs + 1):
    model.train()
    for step, batch in enumerate(train_loader):
        b_input_ids = batch['input_ids'].to(device)
        b_input_mask = batch['attention_mask'].to(device)
        b_labels = batch['label'].to(device)

        #outputs = model(b_input_ids,attention_mask=b_input_mask)
        outputs = model(b_input_ids, attention_mask=b_input_mask, labels=b_labels)

        loss = outputs.loss
        #loss = loss_fn(outputs, b_labels)

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        # modified based on their gradients, the learning rate, etc.
        optimizer.step()
        optimizer.zero_grad()
        
        print(
            "Collecting data from Master Node: \n Train Epoch: {} [{}/{} ({:.0f}%)] Training Loss: {:.6f}".format(
                epoch,
                step * len(batch['input_ids']),
                len(train_loader.dataset),
                100.0 * step / len(train_loader),
                loss.item(),
                )
        )
        test(model, test_loader, device)
        print('Batch', step)
    scheduler.step()



def save_model(model, model_dir):
    path = os.path.join(model_dir, 'model.pth')
    # recommended way from http://pytorch.org/docs/master/notes/serialization.html
    torch.save(model.state_dict(), path)
    #logger.info(f"Saving model: {path} \n")
















































# def _get_train_data_loader(batch_size, training_dir):
#     dataset = pd.read_csv(os.path.join(training_dir, "test.csv"))
#     train_data = ProteinSequenceDataset(
#         sequence=dataset.sequence.to_numpy(),
#         targets=dataset.location.to_numpy(),
#         tokenizer=tokenizer,
#         max_len=MAX_LEN
#   )
#     train_sampler = torch.utils.data.distributed.DistributedSampler(
#             dataset,
#             num_replicas=dist.get_world_size(),
#             rank=dist.get_rank())
#     train_dataloader = DataLoader(train_data, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=True,
#                                   sampler=train_sampler)
#     return train_dataloader


# parser = argparse.ArgumentParser(description='Transfer learning using Transformers')




# args = parser.parse_args()



# model_path = os.path.join(args.model_dir, 'model.pth')
# model_info_path = os.path.join(args.model_dir, 'model_info.pth')
# checkpoint_path = os.path.join(args.output_data_dir, 'model.pth')
# checkpoint_state_path = os.path.join(args.output_data_dir, 'model_info.pth')

# # Set the random seed manually for reproducibility.
# torch.manual_seed(args.seed)

# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# ###############################################################################
# # Load data
# ###############################################################################

# print('Load data')
# corpus = data.Corpus(args.data_dir)


# def batchify(data, bsz):
#     pass


# print('Batchify dataset')
# eval_batch_size = 10
# train_data = batchify(corpus.train, args.batch_size)
# val_data = batchify(corpus.valid, eval_batch_size)
# test_data = batchify(corpus.test, eval_batch_size)


# ###############################################################################
# # Build the model
# ###############################################################################

# print('Build the model')
# ntokens = len(corpus.dictionary)
# rnn_type = 'LSTM'
# model = RNNModel(rnn_type, ntokens, args.emsize, args.nhid, args.nlayers, args.dropout, args.tied).to(device)

# criterion = nn.CrossEntropyLoss()

# # Save the data into model dir to be used with the model later
# for file_name in os.listdir(args.data_dir):
#     full_file_name = os.path.join(args.data_dir, file_name)
#     if os.path.isfile(full_file_name):
#         copy(full_file_name, args.model_dir)

# # Save arguments used to create model for restoring the model later
# with open(model_info_path, 'wb') as f:
#     model_info = {
#         'rnn_type': rnn_type,
#         'ntoken': ntokens,
#         'ninp': args.emsize,
#         'nhid': args.nhid,
#         'nlayers': args.nlayers,
#         'dropout': args.dropout,
#         'tie_weights': args.tied
#     }
#     torch.save(model_info, f)



# def repackage_hidden(h):
#     pass

# def get_batch(source, i):
#     pass

# def evaluate(data_source):
#     pass


# def train():
#     pass




# for epoch in range(1, args.epochs+1):
#     pass


# #save model