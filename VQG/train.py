import argparse
import torch
import torch.nn as nn
import numpy as np
import os
import pickle
import preprocess_get_model
import sys
sys.path.append('skip-thoughts.torch/pytorch')
from skipthoughts import UniSkip
import skimage.io as io
from data_loader import get_loader 
from build_vocab import Vocabulary
from model import T_Att, DecoderRNN 
from torch.autograd import Variable 
from torch.nn.utils.rnn import pack_padded_sequence
from torchvision import transforms
from PIL import Image
import pandas as pd

def to_var(x, volatile=False):
    if torch.cuda.is_available():
        x = x.cuda()
    return Variable(x, volatile=volatile)
    
def main(args):
    # Create model directory
    if not os.path.exists(args.model_path):
        os.makedirs(args.model_path)
    
    # Image preprocessing
    transform = transforms.Compose([ 
        transforms.Resize((224,224)), 
        transforms.ToTensor(), 
        transforms.Normalize((0.485, 0.456, 0.406), 
                             (0.229, 0.224, 0.225))])
    
    # Load vocabulary wrapper.
    with open(args.vocab_path, 'rb') as f:
        vocab = pickle.load(f)
    
    #Load vocab_list for uniskip
    vocab_list = pd.read_csv(args.vocablist_path, header=None)
    vocab_list = vocab_list.values.tolist()[0]
    
    # Build data loader
    data_loader = get_loader(args.image_dir, args.caption_path, args.data_path, vocab, 
                             transform, args.batch_size,
                             shuffle=True, num_workers=args.num_workers) 

    # Build the models
    im_encoder = preprocess_get_model.model()
    attention = T_Att()
    decoder = DecoderRNN(args.embed_size, args.hidden_size, 
                         len(vocab), args.num_layers)
    
    if torch.cuda.is_available():
        im_encoder.cuda()
        attention.cuda()
        decoder.cuda()

    # Loss and Optimizer
    criterion = nn.CrossEntropyLoss()
    params = list(decoder.parameters()) + list(attention.parameters())
    optimizer = torch.optim.Adam(params, lr=args.learning_rate)
    
    # Train the Models
    total_step = len(data_loader)
    for epoch in range(args.num_epochs):
        for i, (images, captions, cap_lengths, qa, qa_lengths, vocab_words) in enumerate(data_loader):
            
            # Set mini-batch dataset
            images = to_var(images, volatile=True)
            captions = to_var(captions)
            qa = to_var(qa)
            targets = pack_padded_sequence(qa, qa_lengths, batch_first=True)[0]

            # Forward, Backward and Optimize
            decoder.zero_grad()
            attention.zero_grad()
            #features = encoder(images)
            img_embeddings = im_encoder(images) 

            uniskip = UniSkip('/Users/tushar/Downloads/code/data/skip-thoughts', vocab_list)
            cap_embeddings = uniskip(captions, cap_lengths)
            cap_embeddings = cap_embeddings.data
            img_embeddings = img_embeddings.data
            ctx_vec = attention(img_embeddings,cap_embeddings)
            outputs = decoder(ctx_vec, qa, qa_lengths)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()

            # Print log info
            if i % args.log_step == 0:
                print('Epoch [%d/%d], Step [%d/%d], Loss: %.4f, Perplexity: %5.4f'
                      %(epoch, args.num_epochs, i, total_step, 
                        loss.data[0], np.exp(loss.data[0]))) 
                
            # Save the models
            if epoch==4:
                torch.save(decoder.state_dict(), 
                           os.path.join(args.model_path, 
                                        'decoder-%d-%d.pkl' %(epoch+1, i+1)))
                torch.save(attention.state_dict(), 
                           os.path.join(args.model_path, 
                                        'attention-%d-%d.pkl' %(epoch+1, i+1)))
            break   
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_path', type=str, default='./models/' ,
                        help='path for saving trained models')
    parser.add_argument('--crop_size', type=int, default=224 ,
                        help='size for randomly cropping images')
    parser.add_argument('--vocab_path', type=str, default='./data/vocab.pkl',
                        help='path for vocabulary wrapper')
    parser.add_argument('--vocablist_path', type=str, default='./data/vocab_list.csv',
                        help='path for vocab list file')
    parser.add_argument('--image_dir', type=str, default='/Users/tushar/Downloads/train2014' ,
                        help='directory for images')
    parser.add_argument('--caption_path', type=str,
                        default='./annotations/captions_train2014.json',
                        help='path for train annotation json file')
    parser.add_argument('--data_path', type=str, default='./dataset.csv' ,
                        help='directory for preprocessed dataset (csv file containing im_id,qid,q,a,captions)')
    parser.add_argument('--log_step', type=int , default=10,
                        help='step size for prining log info')
    parser.add_argument('--save_step', type=int , default=1000,
                        help='step size for saving trained models')
    
    # Model parameters
    parser.add_argument('--embed_size', type=int , default=512 ,
                        help='dimension of word embedding vectors')
    parser.add_argument('--hidden_size', type=int , default=512 ,
                        help='dimension of lstm hidden states')
    parser.add_argument('--num_layers', type=int , default=1 ,
                        help='number of layers in lstm')
    
    parser.add_argument('--num_epochs', type=int, default=5)
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument('--num_workers', type=int, default=1)
    parser.add_argument('--learning_rate', type=float, default=0.001)
    args = parser.parse_args()
    print(args)
    main(args)