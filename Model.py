from Utils.FairGAN import FairGAN
from Utils.DatasetPipeline import DatasetPipeline

# config = {
#     "dataset": "ebnerd_demo",
#     "data_path": "ebnerd_demo/",
#     'epochs': 10,
#     'batch': 64,
#     'ranker_gen_layers': [1000],
#     'ranker_gen_activation': 'tanh',
#     'ranker_gen_dropout': 0.0,
#     'ranker_dis_layers': [1000],
#     'ranker_dis_activation': 'tanh',
#     'ranker_dis_dropout': 0.0,
#     'controller_gen_layers': [1000],
#     'controller_gen_activation': 'relu',
#     'controller_gen_dropout': 0.0,
#     'controller_dis_layers': [1000],
#     'controller_dis_activation': 'relu',
#     'controller_dis_dropout': 0.0,
#     'ranker_gen_step': 2,
#     'ranker_dis_step': 1,
#     'controller_gen_step': 3,
#     'controller_dis_step': 1,
#     'controlling_fairness_step': 3,
#     'ranker_gen_reg': 0.0001,
#     'ranker_dis_reg': 0.0,
#     'controller_gen_reg': 0.0,
#     'controller_dis_reg': 0.0,
#     'controlling_fairness_reg': 0.0,
#     'alpha': 0.001,
#     'lambda': 0.01,
#     'ranker_gen_lr': 1e-5,
#     'ranker_gen_beta1': 0.9,
#     'ranker_dis_lr': 1e-5,
#     'ranker_dis_beta1': 0.9,
#     'controller_gen_lr': 0.001,
#     'controller_gen_beta1': 0.9,
#     'controller_dis_lr': 0.001,
#     'controller_dis_beta1': 0.9,
#     'controlling_fairness_lr': 1e-5,
#     'controlling_fairness_beta1': 0.9,
#     'ranker_initializer': 'glorot_normal',
#     'controller_initializer': 'glorot_normal',
#     'debug': False
# }


class FairGANModel:
    def __init__(self,data,config):
        self.data = data
        self.config = config
        config["n_items"] = self.data.shape[1]
        self.train_ds = DatasetPipeline(labels=self.data.toarray(), conditions=self.data.toarray()).shuffle(1)
        self.model = FairGAN([], **self.config)


    def fit(self):
        
        self.model.fit(self.train_ds.shuffle(self.data.shape[0]).batch(self.config['batch'], True), epochs=self.config['epochs'], callbacks=[])

    def predict(self):
        return self.model.predict(self.train_ds.batch(self.data.shape[0]))

import torch
import torch.optim as optim
from Utils.DiffUtils.gaussian_diffusion import GaussianDiffusion
from Utils.DiffUtils.DNN import DNN
from Utils.DiffUtils.gaussian_diffusion import ModelMeanType
from torch.utils.data import DataLoader

from torch.utils.data import Dataset
import random
import numpy as np

class DataDiffusion(Dataset):
    def __init__(self, data):
        self.data = data
    def __getitem__(self, index):
        item = self.data[index]
        return item
    def __len__(self):
        return len(self.data)

class DiffModel:
    def __init__(self,data,config):
        self.data = data

        self.config = config

        random_seed = 1
        torch.manual_seed(random_seed)
        torch.cuda.manual_seed(random_seed)
        np.random.seed(random_seed)
        random.seed(random_seed)

        def worker_init_fn(worker_id):
            np.random.seed(random_seed + worker_id)

        self.train_loader = DataLoader(DataDiffusion(torch.FloatTensor(data.A)), batch_size=self.config["batch_size"], \
            pin_memory=True, shuffle=True, num_workers=4, worker_init_fn=worker_init_fn)

        self.device = torch.device("cuda:0" if self.config["cuda"] else "cpu")

        if self.config["mean_type"] == 'x0':
            mean_type = ModelMeanType.START_X
        elif self.config["mean_type"] == 'eps':
            mean_type = ModelMeanType.EPSILON
        else:
            raise ValueError("Unimplemented mean type %s" % self.config["mean_type"])

        self.diffusion = GaussianDiffusion(mean_type, self.config["noise_schedule"], \
            self.config["noise_scale"], self.config["noise_min"], self.config["noise_max"], self.config["steps"], self.device).to(self.device)
        
        out_dims = self.config["dims"] + [self.data.shape[1]]
        in_dims = out_dims[::-1]

        self.model = DNN(in_dims, out_dims, self.config["emb_size"], time_type="cat", norm=self.config["norm"]).to(self.device)
        self.optimizer = optim.AdamW(self.model.parameters(), lr=self.config["lr"], weight_decay=self.config["weight_decay"])

    def fit(self):

        batch_count = 0
        total_loss = 0.0

        for epoch in range(1, self.config["epochs"] + 1):
            self.model.train()
            for batch_idx, batch in enumerate(self.train_loader):
                batch = batch.to(self.device)
                batch_count += 1
                self.optimizer.zero_grad()
                losses = self.diffusion.training_losses(self.model, batch, self.config["reweight"])
                loss = losses["loss"].mean()
                total_loss += loss
                loss.backward()
                self.optimizer.step()
            print(f'Runing Epoch {epoch}')
            print('---'*18)