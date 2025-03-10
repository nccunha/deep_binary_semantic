'''
original implementation: https://github.com/trypag/pytorch-unet-segnet

'''

import torch.nn as nn
import torch.nn.functional as F


class SegNet(nn.Module):
    """SegNet: A Deep Convolutional Encoder-Decoder Architecture for
    Image Segmentation. https://arxiv.org/abs/1511.00561
    See https://github.com/alexgkendall/SegNet-Tutorial for original models.
    Args:
        num_classes (int): number of classes to segment
        n_init_features (int): number of input features in the fist convolution
        drop_rate (float): dropout rate of each encoder/decoder module
        filter_config (list of 5 ints): number of output features at each level
    """
    def __init__(self, num_classes, n_init_features=1, drop_rate=0.05,
                 filter_config=(64, 128, 256, 512, 512)):
        super(SegNet, self).__init__()
        self.num_classes = num_classes
        self.n_init_features = n_init_features
        self.encoders = nn.ModuleList()
        self.decoders = nn.ModuleList()

        if not isinstance(filter_config,tuple):
            filter_config  =tuple(filter_config)

        # setup number of conv-bn-relu blocks per module and number of filters
        encoder_n_layers = (2, 2, 2, 2, 3)
        encoder_filter_config = (filter_config,) + filter_config
        decoder_n_layers = (3, 2, 2, 2, 1)
        decoder_filter_config = filter_config[::-1] + (filter_config[0],)

        for i in range(0, 5):
            # encoder architecture
            self.encoders.append(_Encoder(encoder_filter_config[i],
                                          encoder_filter_config[i + 1],
                                          encoder_n_layers[i], drop_rate))

            # decoder architecture
            self.decoders.append(_Decoder(decoder_filter_config[i],
                                          decoder_filter_config[i + 1],
                                          decoder_n_layers[i], drop_rate))

        # final classifier (equivalent to a fully connected layer)
        self.classifier = nn.Conv2d(filter_config[0], num_classes, kernel_size=1, padding=0, stride=1, bias=False)
        #self.classifier = nn.Conv2d(filter_config[0], num_classes, 1, 0, 1)

    def __str__(self):
        return type(self).__name__  + f'\n Num class: {self.num_classes} \n Input chanels: {self.n_init_features}\n' 

    def get_backbone_params(self):
        
        return self.encoders.parameters()

    def get_classifier_params(self):
        from itertools import chain
        return list(chain(self.decoders.parameters(),self.classifier.parameters()))

    def forward(self, x):
        indices = []
        unpool_sizes = []
        feat = x

        feat_vec = []
        # encoder path, keep track of pooling indices and features size
        for i in range(0, 5):
            (feat, ind), size = self.encoders[i](feat)
            indices.append(ind)
            unpool_sizes.append(size)
            feat_vec.append(feat.detach())
        
        # invert order
        feat_vec = feat_vec[::-1]
        # decoder path, upsampling with corresponding indices and size
        for i in range(0, 5):
            
            feat =  self.decoders[i](feat, indices[4 - i], unpool_sizes[4 - i])
            if i<4:
                feat = feat + feat_vec[i+1]
            

        return self.classifier(feat),feat_vec


class _Encoder(nn.Module):
    def __init__(self, n_in_feat, n_out_feat, n_blocks=2, drop_rate=0.5):
        """Encoder layer follows VGG rules + keeps pooling indices
        Args:
            n_in_feat (int): number of input features
            n_out_feat (int): number of output features
            n_blocks (int): number of conv-batch-relu block inside the encoder
            drop_rate (float): dropout rate to use
        """
        super(_Encoder, self).__init__()

        layers = [nn.Conv2d(n_in_feat, n_out_feat, 3, 1, 1),
                  nn.BatchNorm2d(n_out_feat),
                  #nn.ReLU(inplace=True)
                  nn.ReLU6(inplace=True)
                  
                  ]

        if n_blocks > 1:
            layers += [nn.Conv2d(n_out_feat, n_out_feat, 3, 1, 1),
                       nn.BatchNorm2d(n_out_feat),
                       #nn.ReLU(inplace=True)
                       nn.ReLU6(inplace=True)
                       
                       ]
                       
            if n_blocks == 3:
                layers += [nn.Dropout(drop_rate)]

        self.features = nn.Sequential(*layers)

    def forward(self, x):
        output = self.features(x)
        return F.max_pool2d(output, 2, 2, return_indices=True), output.size()


class _Decoder(nn.Module):
    """Decoder layer decodes the features by unpooling with respect to
    the pooling indices of the corresponding decoder part.
    Args:
        n_in_feat (int): number of input features
        n_out_feat (int): number of output features
        n_blocks (int): number of conv-batch-relu block inside the decoder
        drop_rate (float): dropout rate to use
    """
    def __init__(self, n_in_feat, n_out_feat, n_blocks=2, drop_rate=0.5):
        super(_Decoder, self).__init__()

        layers = [nn.Conv2d(n_in_feat, n_in_feat, 3, 1, 1),
                    nn.BatchNorm2d(n_in_feat),
                    #nn.ReLU(inplace=True)
                    nn.ReLU6(inplace=True),
                  
                  ]

        if n_blocks > 1:
            layers += [nn.Conv2d(n_in_feat, n_out_feat, 3, 1, 1),
                       nn.BatchNorm2d(n_out_feat),
                       nn.ReLU6(inplace=True)
                 ]
                       
            if n_blocks == 3:
                layers += [nn.Dropout(drop_rate)]

        self.features = nn.Sequential(*layers)

    def forward(self, x, indices, size):
        unpooled = F.max_unpool2d(x, indices, 2, 2, 0, size)
        return self.features(unpooled)
