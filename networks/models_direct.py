from networks.models_utils import *
from torch import nn, einsum
import torch
import torch.nn.functional as F
from pn2_utils import PointNet_SA_Module_KNN, Transformer


# -------------------------------------Encoder-----------------------------------
# Resnet Blocks
class ResnetBlockFC(nn.Module):
    """ Fully connected ResNet Block class.
    Args:
        size_in (int): input dimension
        size_out (int): output dimension
        size_h (int): hidden dimension
    """

    def __init__(self, size_in, size_out=None, size_h=None):
        super().__init__()
        # Attributes
        if size_out is None:
            size_out = size_in

        if size_h is None:
            size_h = min(size_in, size_out)

        self.size_in = size_in
        self.size_h = size_h
        self.size_out = size_out
        # Submodules
        self.fc_0 = nn.Linear(size_in, size_h)
        self.fc_1 = nn.Linear(size_h, size_out)
        self.relu1 = nn.ReLU()
        self.relu2 = nn.ReLU()

        if size_in == size_out:
            self.shortcut = None
        else:
            self.shortcut = nn.Linear(size_in, size_out, bias=False)
        # Initialization
        nn.init.zeros_(self.fc_1.weight)

    def forward(self, x):
        net = self.fc_0(self.relu1(x))
        dx = self.fc_1(self.relu2(net))

        if self.shortcut is not None:
            x_s = self.shortcut(x)
        else:
            x_s = x

        return x_s + dx


# 带Resnet的Pointnet（完整的点云特征提取）
class ResnetPointnet(nn.Module):
    """ PointNet-based encoder network with ResNet blocks.
    Args:
        c_dim (int): dimension of latent code c
        dim (int): input points dimension
        hidden_dim (int): hidden dimension of the network
    """

    def __init__(self, c_dim=128, dim=3, hidden_dim=128):
        super().__init__()
        self.c_dim = c_dim
        self.fc_pos = nn.Linear(dim, 2 * hidden_dim)

        # 每个ResnetBlock的维度为(2 * hidden_dim, hidden_dim)，这是因为需要与池化后结果进行拼接
        self.block_0 = ResnetBlockFC(2 * hidden_dim, hidden_dim)
        self.block_1 = ResnetBlockFC(2 * hidden_dim, hidden_dim)
        self.block_2 = ResnetBlockFC(2 * hidden_dim, hidden_dim)
        self.block_3 = ResnetBlockFC(2 * hidden_dim, hidden_dim)
        self.block_4 = ResnetBlockFC(2 * hidden_dim, hidden_dim)
        self.fc_c = nn.Linear(hidden_dim, c_dim)

        self.actvn = nn.ReLU()
        self.pool = maxpool

    def forward(self, p):
        # batch_size, T, D = p.size()
        # output size: B x T X F

        net = self.fc_pos(p)
        # 每轮计算完毕后进行最大池化，将池化结果进行拓展，然后进行拼接
        net = self.block_0(net)
        pooled = self.pool(net, dim=1, keepdim=True).expand(net.size())
        net = torch.cat([net, pooled], dim=2)

        net = self.block_1(net)
        pooled = self.pool(net, dim=1, keepdim=True).expand(net.size())
        net = torch.cat([net, pooled], dim=2)

        net = self.block_2(net)
        pooled = self.pool(net, dim=1, keepdim=True).expand(net.size())
        net = torch.cat([net, pooled], dim=2)

        net = self.block_3(net)
        pooled = self.pool(net, dim=1, keepdim=True).expand(net.size())
        net = torch.cat([net, pooled], dim=2)

        net = self.block_4(net)
        # Recude to  B x F
        net = self.pool(net, dim=1)

        c = self.fc_c(self.actvn(net))

        return c


class PN2_Transformer_Encoder(nn.Module):
    def __init__(self, out_dim=1024):
        """Encoder that encodes information of partial point cloud"""
        super().__init__()
        self.sa_module_1 = PointNet_SA_Module_KNN(512, 16, 3, [64, 128], group_all=False, if_bn=False, if_idx=True)
        self.transformer_1 = Transformer(128, dim=64)
        self.sa_module_2 = PointNet_SA_Module_KNN(128, 16, 128, [128, 256], group_all=False, if_bn=False, if_idx=True)
        self.transformer_2 = Transformer(256, dim=64)
        self.sa_module_3 = PointNet_SA_Module_KNN(None, None, 256, [512, out_dim], group_all=True, if_bn=False)

    def forward(self, point_cloud):
        """
        Args:
        point_cloud: b, 3, n

        Returns:
        l3_points: (B, out_dim, 1)
        """
        l0_xyz = point_cloud
        l0_points = point_cloud

        l1_xyz, l1_points, idx1 = self.sa_module_1(l0_xyz, l0_points)  # (B, 3, 512), (B, 128, 512)
        l1_points = self.transformer_1(l1_points, l1_xyz)
        l2_xyz, l2_points, idx2 = self.sa_module_2(l1_xyz, l1_points)  # (B, 3, 128), (B, 256, 512)
        l2_points = self.transformer_2(l2_points, l2_xyz)
        l3_xyz, l3_points = self.sa_module_3(l2_xyz, l2_points)  # (B, 3, 1), (B, out_dim, 1)

        return l3_points


class CombinedDecoder(nn.Module):
    def __init__(
            self,
            latent_size,
            dims,
            dropout=None,
            dropout_prob=0.0,
            norm_layers=(),
            latent_in=(),
            weight_norm=False,
            xyz_in_all=None,
            use_tanh=False,
            latent_dropout=False,
            use_classifier=False,
    ):
        super(CombinedDecoder, self).__init__()

        dims = [latent_size + 3] + dims + [1]  # <<<< 2 outputs instead of 1.

        self.num_layers = len(dims)
        self.norm_layers = norm_layers
        self.latent_in = latent_in
        self.latent_dropout = latent_dropout
        if self.latent_dropout:
            self.lat_dp = nn.Dropout(0.2)

        self.xyz_in_all = xyz_in_all
        self.weight_norm = weight_norm
        self.use_classifier = use_classifier

        for layer in range(0, self.num_layers - 1):
            if layer + 1 in latent_in:
                out_dim = dims[layer + 1] - dims[0]
            else:
                out_dim = dims[layer + 1]
                if self.xyz_in_all and layer != self.num_layers - 2:
                    out_dim -= 3
            # print("out dim  out_dim)

            if weight_norm and layer in self.norm_layers:
                setattr(
                    self,
                    "lin" + str(layer),
                    nn.utils.weight_norm(nn.Linear(dims[layer], out_dim)),
                )
            else:
                setattr(self, "lin" + str(layer), nn.Linear(dims[layer], out_dim))

            if (
                    (not weight_norm)
                    and self.norm_layers is not None
                    and layer in self.norm_layers
            ):
                setattr(self, "bn" + str(layer), nn.LayerNorm(out_dim))

            # classifier
            if self.use_classifier and layer == self.num_layers - 2:
                self.classifier_head = nn.Linear(dims[layer], self.num_class)

        self.use_tanh = use_tanh
        if use_tanh:
            self.tanh = nn.Tanh()
        self.relu = nn.ReLU()

        self.dropout_prob = dropout_prob
        self.dropout = dropout
        self.th = nn.Tanh()

    # input: N x (L+3)
    def forward(self, input):
        xyz = input[:, -3:]

        if input.shape[1] > 3 and self.latent_dropout:
            latent_vecs = input[:, :-3]
            latent_vecs = F.dropout(latent_vecs, p=0.2, training=self.training)
            x = torch.cat([latent_vecs, xyz], 1)
        else:
            x = input

        for layer in range(0, self.num_layers - 1):

            lin = getattr(self, "lin" + str(layer))
            if layer in self.latent_in:
                x = torch.cat([x, input], 1)
            elif layer != 0 and self.xyz_in_all:
                x = torch.cat([x, xyz], 1)
            x = lin(x)
            # last layer Tanh
            if layer == self.num_layers - 2 and self.use_tanh:
                x = self.tanh(x)
            if layer < self.num_layers - 2:
                if (
                        self.norm_layers is not None
                        and layer in self.norm_layers
                        and not self.weight_norm
                ):
                    bn = getattr(self, "bn" + str(layer))
                    x = bn(x)
                x = self.relu(x)
                if self.dropout is not None and layer in self.dropout:
                    x = F.dropout(x, p=self.dropout_prob, training=self.training)

        if hasattr(self, "th"):
            x = self.th(x)

        return x[:, 0].unsqueeze(1)


class IBSNet(nn.Module):
    def __init__(self, encoder_obj1, encoder_obj2, decoder, num_samp_per_scene):
        super().__init__()
        self.encoder_obj1 = encoder_obj1
        self.encoder_obj2 = encoder_obj2
        self.decoder = decoder
        self.num_samp_per_scene = num_samp_per_scene

    def forward(self, x_obj1, x_obj2, xyz):
        x_obj1 = self.encoder_obj1(x_obj1)
        latent_obj1 = x_obj1.repeat_interleave(self.num_samp_per_scene, dim=0)
        x_obj2 = self.encoder_obj2(x_obj2)
        latent_obj2 = x_obj2.repeat_interleave(self.num_samp_per_scene, dim=0)

        latent = torch.cat([latent_obj1, latent_obj2], 1)

        decoder_inputs = torch.cat([latent, xyz], 1)
        udf_obj1, udf_obj2 = self.decoder(decoder_inputs)
        return udf_obj1, udf_obj2


class IBSNet_transformer(nn.Module):
    def __init__(self, encoder_obj1, encoder_obj2, decoder, num_samp_per_scene):
        super().__init__()
        self.encoder_obj1 = encoder_obj1
        self.encoder_obj2 = encoder_obj2
        self.decoder = decoder
        self.num_samp_per_scene = num_samp_per_scene

    def forward(self, x_obj1, x_obj2, xyz):
        x_obj1 = x_obj1.permute(0, 2, 1)
        x_obj1 = self.encoder_obj1(x_obj1)
        x_obj1 = x_obj1.permute(0, 2, 1)
        latent_obj1 = x_obj1.repeat_interleave(self.num_samp_per_scene, dim=0)

        x_obj2 = x_obj2.permute(0, 2, 1)
        x_obj2 = self.encoder_obj2(x_obj2)
        x_obj2 = x_obj2.permute(0, 2, 1)
        latent_obj2 = x_obj2.repeat_interleave(self.num_samp_per_scene, dim=0)

        latent = torch.cat([latent_obj1, latent_obj2], 1)

        decoder_inputs = torch.cat([latent, xyz], 1)
        udf_pred = self.decoder(decoder_inputs)
        return udf_pred
