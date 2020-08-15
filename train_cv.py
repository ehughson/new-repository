import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import pandas as pd
import numpy as np
from torch.utils.data import TensorDataset, DataLoader, random_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from numpy import vstack
from network import ContemptNet
from sklearn.model_selection import StratifiedKFold, KFold
import matplotlib.pyplot as plt

# https://www.kaggle.com/super13579/pytorch-nn-cyclelr-k-fold-0-897-lightgbm-0-899#Pytorch-to-implement-simple-feed-forward-NN-model-(0.89+)
le = LabelEncoder()
def train_model(train_dl, model, criterion, optimizer):
    training_loss = []
    avg_loss = 0
    for i, data in enumerate(train_dl):
        # print()

        inputs, labels = data
        inputs = inputs.cuda()
        labels = labels.cuda()
        model = model.train()
        # forward + backward + optimize
        yhat = model(inputs)
        loss = criterion(yhat, labels)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        training_loss.append(loss.item())
    return np.mean(training_loss)

# make a class prediction for one row of data

def predict(row, model):
    # convert row to data
    row = torch.tensor([row], dtype=torch.float32).cuda()
    model.eval()
    # make prediction
    yhat = model(row)
    # retrieve numpy array
    yhat = yhat.detach().cpu().numpy()
    return np.argmax(yhat)
    

def valid_model(valid_dl, model, criterion):
    valid_loss = []
    valid_acc = []
    predictions, actuals = list(), list()
    model.eval()
    for i, data in enumerate(valid_dl):
        inputs, targets = data
        inputs = inputs.cuda()
        targets = targets.cuda()
        # retrieve numpy array
        yhat = model(inputs)
        # print("yhat shape: ", yhat.shape)
         # retrieve numpy array
        loss = criterion(yhat, targets)
        yhat = yhat.cpu().detach().numpy()
        actual = targets.cpu().numpy()
        # convert to class labels
        yhat = np.argmax(yhat, axis=1)
        # reshape for stacking
        actual = actual.reshape((len(actual), 1))
        yhat = yhat.reshape((len(yhat), 1))
        # calculate accuracy
        predictions.append(yhat)
        actuals.append(actual)
        acc = accuracy_score(vstack(predictions), vstack(actuals))
        # round to class values
        # yhat = yhat.reshape((len(yhat), 1))
        valid_loss.append(loss.item())
        valid_acc.append(acc)

    # f1 = f1_score(actuals, predictions)
    f1_metric = f1_score(vstack(actuals), vstack(predictions), average = "macro")
    print('F1 score:' , f1_metric)
    return np.mean(valid_loss), np.mean(valid_acc)

def get_dataloaders(df, batch_size, valid_culture=None):
        
    ### For random splitting
    # if valid_culture is None:
    Y = df[['emotion']].values
    X = df.drop(['frame', 'face_id', 'culture', 'filename', 'emotion', 'confidence','success'], axis=1)
    Y = le.fit_transform(Y)
    Y_tensor = torch.tensor(Y, dtype=torch.long)
    X_tensor = torch.tensor(X.values, dtype=torch.float32)
    
    dataset = TensorDataset(X_tensor, Y_tensor)

    dataloader = DataLoader(dataset, shuffle=True, batch_size=batch_size)
    # valid_dataloader = DataLoader(valid, shuffle=False, batch_size=batch_size)
    # test_dataloader = DataLoader(test,  shuffle=False, batch_size=batch_size)
    return dataloader


# net = ContemptNet()
# if torch.cuda.is_available():
#     net.cuda()
# print(net)
batch_size = 32
epochs = 100


data_path = './processed_data_csv/all_videos.csv'
df = pd.read_csv(data_path)
## TODO: before doing this part, remember to pick the 'test' sections
kfold = KFold(5, True, 1)
videos = df['filename'].unique()
test_videos = pd.Series(videos).sample(frac=0.10)
# print(test_videos)
# videos must be array to be subscriptable by a list
videos = np.array(list(set(videos) - set(test_videos)))
# Removing test videos from train dataset
test_df = df[df['filename'].isin(test_videos)]
df = df[~df['filename'].isin(list(test_videos))]
splits = kfold.split(videos)
test_df_copy = test_df.drop(['frame', 'face_id', 'culture', 'filename', 'emotion', 'confidence','success'], axis=1)
for (i, (train, test)) in enumerate(splits):
    print('%d-th split: train: %d, test: %d' % (i+1, len(videos[train]), len(videos[test])))
    train_df = df[df['filename'].isin(videos[train])]
    valid_df = df[df['filename'].isin(videos[test])]
    # print('train length:', len(train_df))
    # print('valid length:', len(valid_df))
    train_dataloader = get_dataloaders(df, batch_size)
    valid_dataloader = get_dataloaders(valid_df, batch_size)
    net = ContemptNet()
    if torch.cuda.is_available():
        net.cuda()
    # optimizer = optim.Adam(net.parameters(), lr=0.005, weight_decay=1e-5)
    optimizer = optim.ASGD(net.parameters(), lr=0.005)
    criterion = nn.CrossEntropyLoss()
    train_losses = []
    valid_losses = []
    for epoch in range(epochs):
        print('Epoch {}/{}'.format(epoch, epochs - 1))
        print('-' * 10)
        epoch_train_loss = train_model(train_dataloader, net, criterion, optimizer)
        epoch_valid_loss, epoch_valid_acc = valid_model(valid_dataloader, net, criterion)
        train_losses.append(epoch_train_loss)
        valid_losses.append(epoch_valid_loss)
        print('[%d] Training loss: %.3f' %
                    (epoch + 1, epoch_train_loss ))
        print('[%d] Validation loss: %.3f' %
                    (epoch + 1, epoch_valid_loss ))
        print('[%d] Validation accuracy: %.3f' %
                    (epoch + 1, epoch_valid_acc ))
    ## Plot the curves
    plt.plot(train_losses, label='training loss')
    plt.plot(valid_losses, label='validation loss')
    # plt.legend(loc="lower right")
    plt.legend(bbox_to_anchor=(1.05, 1.0), loc='upper left')
    plt.show()

    ## Testing
    Yhat = list()
    # Y = le.fit_transform(test_df['emotion'].values)

    for row in test_df_copy.values:
        p = predict(row, net)
        # p = p.reshape((len(p), 1))
        Yhat.append(p)

    # test_df['integer_emotion'] = Y
    test_df['predicted'] = le.inverse_transform(Yhat)
    # print('Len test_df: ', len(test_df))
    # print('Len Y:', len(Y))
    # print(test_df.sample(25))
    print('Test accuracy: %.3f' % (accuracy_score(le.fit_transform(test_df['emotion'].values), Yhat)))
    # actual = actual.reshape((len(actual), 1))
    # yhat = yhat.reshape((len(yhat), 1))