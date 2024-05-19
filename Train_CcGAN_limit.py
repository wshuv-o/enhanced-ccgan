
import torch
import torch.nn as nn
from torchvision.utils import save_image
import numpy as np
import os
import timeit

from utils import *
from opts import parse_opts

''' Settings '''
args = parse_opts()
NGPU = torch.cuda.device_count()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# some parameters in opts
niters = args.niters_gan
resume_niters = args.resume_niters_gan
dim_gan = args.dim_gan
lr_g = args.lr_g_gan
lr_d = args.lr_d_gan
save_niters_freq = args.save_niters_freq
batch_size = min(args.batch_size_disc, args.batch_size_gene)
num_classes = args.cGAN_num_classes

NC = args.num_channels
IMG_SIZE = args.img_size
print(niters, resume_niters, dim_gan, lr_d, lr_g, save_niters_freq, batch_size, num_classes, NC, IMG_SIZE)

def train_CcGAN_limit(images, labels, netG, netD, save_images_folder, save_models_folder = None):

    netG = netG.to(device)
    netD = netD.to(device)

    criterion = nn.BCELoss()
    optimizerG = torch.optim.Adam(netG.parameters(), lr=lr_g, betas=(0.5, 0.999))
    optimizerD = torch.optim.Adam(netD.parameters(), lr=lr_d, betas=(0.5, 0.999))

    trainset = IMGs_dataset(images, labels, normalize=True)
    train_dataloader = torch.utils.data.DataLoader(trainset, batch_size=batch_size, shuffle=True, num_workers=8)
    unique_labels = np.sort(np.array(list(set(labels)))).astype(np.int)

    if save_models_folder is not None and resume_niters>0:
        save_file = save_models_folder + "/CcGAN_limit_checkpoint_intrain/CcGAN_limit_checkpoint_niters_{}.pth".format(resume_niters)
        checkpoint = torch.load(save_file)
        netG.load_state_dict(checkpoint['netG_state_dict'])
        netD.load_state_dict(checkpoint['netD_state_dict'])
        optimizerG.load_state_dict(checkpoint['optimizerG_state_dict'])
        optimizerD.load_state_dict(checkpoint['optimizerD_state_dict'])
        torch.set_rng_state(checkpoint['rng_state'])
    #end if

    # printed images with labels between the 5-th quantile and 95-th quantile of training labels
    n_row=10; n_col = n_row
    z_fixed = torch.randn(n_row*n_col, dim_gan, dtype=torch.float).to(device)
    start_label = np.quantile(train_labels, 0.05)
    end_label = np.quantile(train_labels, 0.95)
    selected_labels = np.linspace(start_label, end_label, num=n_row)
    y_fixed = np.zeros(n_row*n_col)
    for i in range(n_row):
        curr_label = selected_labels[i]
        for j in range(n_col):
            y_fixed[i*n_col+j] = curr_label
    print(y_fixed)
    y_fixed = torch.from_numpy(y_fixed).type(torch.float).view(-1,1).to(device)


    batch_idx = 0
    dataloader_iter = iter(train_dataloader)

    start_time = timeit.default_timer()
    for niter in range(resume_niters, niters):

        if batch_idx+1 == len(train_dataloader):
            dataloader_iter = iter(train_dataloader)
            batch_idx = 0

        # training images
        batch_train_images, batch_train_labels = dataloader_iter.next()
        assert batch_size == batch_train_images.shape[0]
        batch_train_images = batch_train_images.type(torch.float).to(device)
        batch_train_labels = batch_train_labels.type(torch.float).to(device)

        # Adversarial ground truths
        GAN_real = torch.ones(batch_size,1).to(device)
        GAN_fake = torch.zeros(batch_size,1).to(device)

        '''

        Train Generator: maximize log(D(G(z)))

        '''
        netG.train()

        # Sample noise and labels as generator input
        z = torch.randn(batch_size, dim_gan, dtype=torch.float).to(device)

        #generate fake images
        batch_fake_images = netG(z, batch_train_labels)

        # Loss measures generator's ability to fool the discriminator
        dis_out = netD(batch_fake_images, batch_train_labels)

        #generator try to let disc believe gen_imgs are real
        g_loss = criterion(dis_out, GAN_real)

        optimizerG.zero_grad()
        g_loss.backward()
        optimizerG.step()

        '''

        Train Discriminator: maximize log(D(x)) + log(1 - D(G(z)))

        '''

        # Measure discriminator's ability to classify real from generated samples
        prob_real = netD(batch_train_images, batch_train_labels)
        prob_fake = netD(batch_fake_images.detach(), batch_train_labels.detach())
        real_loss = criterion(prob_real, GAN_real)
        fake_loss = criterion(prob_fake, GAN_fake)
        d_loss = (real_loss + fake_loss) / 2

        optimizerD.zero_grad()
        d_loss.backward()
        optimizerD.step()

        batch_idx+=1

        if (niter+1)%20 == 0:
            print ("CcGAN limit: [Iter %d/%d] [D loss: %.4f] [G loss: %.4f] [D prob real:%.4f] [D prob fake:%.4f] [Time: %.4f]" % (niter+1, niters, d_loss.item(), g_loss.item(), prob_real.mean().item(),prob_fake.mean().item(), timeit.default_timer()-start_time))


        if (niter+1) % 100 == 0:
            netG.eval()
            with torch.no_grad():
                gen_imgs = netG(z_fixed, y_fixed)
                gen_imgs = gen_imgs.detach()
            save_image(gen_imgs.data, save_images_folder +'/{}.png'.format(niter+1), nrow=n_row, normalize=True)

        if save_models_folder is not None and ((niter+1) % save_niters_freq == 0 or (niter+1) == niters):
            save_file = save_models_folder + "/CcGAN_limit_checkpoint_intrain/CcGAN_limit_checkpoint_niters_{}.pth".format(niter+1)
            os.makedirs(os.path.dirname(save_file), exist_ok=True)
            torch.save({
                    'netG_state_dict': netG.state_dict(),
                    'netD_state_dict': netD.state_dict(),
                    'optimizerG_state_dict': optimizerG.state_dict(),
                    'optimizerD_state_dict': optimizerD.state_dict(),
                    'rng_state': torch.get_rng_state()
            }, save_file)
    #end for niter


    return netG, netD



def SampCcGAN_given_labels(netG, labels, path=None, NFAKE = 10000, batch_size = 500):
    '''
    labels: a numpy array; normalized label in [0,1]
    '''
    assert len(labels) == NFAKE
    if batch_size>NFAKE:
        batch_size = NFAKE
    fake_images = np.zeros((NFAKE+batch_size, NC, IMG_SIZE, IMG_SIZE), dtype=np.float)
    fake_labels = np.concatenate((labels, labels[0:batch_size]))
    netG=netG.to(device)
    netG.eval()

    with torch.no_grad():
        pb = SimpleProgressBar()
        tmp = 0
        while tmp < NFAKE:
            z = torch.randn(batch_size, dim_gan, dtype=torch.float).to(device)
            y = torch.from_numpy(fake_labels[tmp:(tmp+batch_size)]).type(torch.float).view(-1,1).to(device)
            batch_fake_images = netG(z, y)
            fake_images[tmp:(tmp+batch_size)] = batch_fake_images.cpu().detach().numpy()
            tmp += batch_size
            pb.update(min(float(tmp)/NFAKE, 1)*100)

    #remove extra entries
    fake_images = fake_images[0:NFAKE]
    fake_labels = fake_labels[0:NFAKE]

    if path is not None:
        raw_fake_images = (fake_images*0.5+0.5)*255.0
        raw_fake_images = raw_fake_images.astype(np.uint8)
        for i in range(NFAKE):
            filename = path + '/' + str(i) + '.jpg'
            im = Image.fromarray(raw_fake_images[i][0], mode='L')
            im = im.save(filename)

    return fake_images, fake_labels

def SampCcGAN_given_label(netG, label, path=None, NFAKE = 10000, batch_size = 500):
    '''
    label: a scalar; normalized label in [0,1]
    '''
    if batch_size>NFAKE:
        batch_size = NFAKE
    fake_images = np.zeros((NFAKE+batch_size, NC, IMG_SIZE, IMG_SIZE), dtype=np.float)
    netG=netG.to(device)
    netG.eval()

    with torch.no_grad():
        tmp = 0
        while tmp < NFAKE:
            z = torch.randn(batch_size, dim_gan, dtype=torch.float).to(device)
            y = np.ones(batch_size) * label
            y = torch.from_numpy(y).type(torch.float).view(-1,1).to(device)
            batch_fake_images = netG(z, y)
            fake_images[tmp:(tmp+batch_size)] = batch_fake_images.cpu().detach().numpy()
            tmp += batch_size

    #remove extra entries
    fake_images = fake_images[0:NFAKE]
    fake_labels = np.ones(NFAKE) * label #use assigned label

    if path is not None:
        raw_fake_images = (fake_images*0.5+0.5)*255.0
        raw_fake_images = raw_fake_images.astype(np.uint8)
        for i in range(NFAKE):
            filename = path + '/' + str(i) + '.jpg'
            im = Image.fromarray(raw_fake_images[i][0], mode='L')
            im = im.save(filename)

    return fake_images, fake_labels
