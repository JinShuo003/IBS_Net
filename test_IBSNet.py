import os.path
import re

import numpy as np
import torch

import deep_sdf.workspace as ws
import torch.utils.data as data_utils
import json
import deep_sdf
import open3d as o3d


def get_spec_with_default(specs, key, default):
    try:
        return specs[key]
    except KeyError:
        return default


def visualize_data(pcd1, pcd2, udf_data, specs):
    # 将udf数据拆分开，并且转移到cpu
    udf_np = udf_data.cpu().detach().numpy()
    pcd1_np = pcd1.cpu().detach().numpy()
    pcd2_np = pcd2.cpu().detach().numpy()

    udf_np = np.split(udf_np, pcd1_np.shape[0])
    for i in range(pcd1_np.shape[0]):
        ibs_points = [points[0:3] for points in udf_np[i] if abs(points[3] - points[4]) < specs['IBSSurfaceThreshold']]

        pcd1_o3d = o3d.geometry.PointCloud()
        pcd2_o3d = o3d.geometry.PointCloud()
        ibs_o3d = o3d.geometry.PointCloud()

        pcd1_o3d.points = o3d.utility.Vector3dVector(pcd1_np[i])
        pcd2_o3d.points = o3d.utility.Vector3dVector(pcd2_np[i])
        ibs_o3d.points = o3d.utility.Vector3dVector(ibs_points)

        pcd1_o3d.paint_uniform_color([1, 0, 0])
        pcd2_o3d.paint_uniform_color([0, 1, 0])
        ibs_o3d.paint_uniform_color([0, 0, 1])

        o3d.visualization.draw_geometries([ibs_o3d, pcd1_o3d, pcd2_o3d])


def save_result(sdf_test_loader, indices, specs, udf_data):
    scenes_per_batch = specs["ScenesPerBatch"]
    save_dir = specs["SaveDir"]

    # 将udf数据拆分开，并且转移到cpu
    udf_np = udf_data.cpu().detach().numpy()
    udf_np = np.split(udf_np, scenes_per_batch)

    filename_list = [sdf_test_loader.dataset.npyfiles[index] for index in indices]
    for index, filename in enumerate(filename_list):
        filename_info = os.path.split(filename)
        filename_ = filename_info[-1]
        category = filename_info[-2]
        save_path = os.path.join(save_dir, category)

        if not os.path.isdir(save_path):
            os.makedirs(save_path)
        np.savez(os.path.join(save_path, filename_), data=udf_np[index])


def get_dataloader(specs):
    data_source = specs["DataSource"]
    test_split_file = specs["TestSplit"]
    num_samp_per_scene = specs["SamplesPerScene"]
    scene_per_batch = specs["ScenesPerBatch"]
    num_data_loader_threads = get_spec_with_default(specs, "DataLoaderThreads", 1)

    with open(test_split_file, "r") as f:
        test_split = json.load(f)

    sdf_test_dataset = deep_sdf.data.SDFSamples(
        data_source, test_split, num_samp_per_scene, load_ram=False
    )

    sdf_test_loader = data_utils.DataLoader(
        sdf_test_dataset,
        batch_size=scene_per_batch,
        shuffle=True,
        num_workers=num_data_loader_threads,
        drop_last=False,
    )

    return sdf_test_loader


def test(IBS_Net, sdf_test_loader, specs, model):
    scene_per_batch = specs["ScenesPerBatch"]
    num_samp_per_scene = specs["SamplesPerScene"]
    test_result_dir = specs["TestResult"]
    test_split = specs["TestSplit"]
    device = specs["Device"]
    visualize = specs["Visualize"]
    save = specs["Save"]

    loss_udf1 = torch.nn.L1Loss(reduction="sum")
    loss_udf2 = torch.nn.L1Loss(reduction="sum")
    with torch.no_grad():
        test_total_loss = 0
        for pcd1, pcd2, sdf_data, indices in sdf_test_loader:
            sdf_data = sdf_data.reshape(-1, 5)

            pcd1.requires_grad = False
            pcd2.requires_grad = False
            sdf_data.requires_grad = False

            xyz = sdf_data[:, 0:3]
            udf_gt1 = sdf_data[:, 3].unsqueeze(1)
            udf_gt2 = sdf_data[:, 4].unsqueeze(1)

            pcd1 = pcd1.to(device)
            pcd2 = pcd2.to(device)
            xyz = xyz.to(device)

            udf_pred1, udf_pred2 = IBS_Net(pcd1, pcd2, xyz)

            batch_loss1 = loss_udf1(udf_pred1, udf_gt1.to(device)) / (scene_per_batch * num_samp_per_scene)
            batch_loss2 = loss_udf2(udf_pred2, udf_gt2.to(device)) / (scene_per_batch * num_samp_per_scene)
            batch_loss = (batch_loss1 + batch_loss2) / 2

            test_total_loss += batch_loss.item()

            udf_data = torch.cat([xyz, udf_pred1, udf_pred2], 1)
            if save:
                save_result(sdf_test_loader, indices, specs, udf_data)
            if visualize:
                visualize_data(pcd1, pcd2, udf_data, specs)

        test_avrg_loss = test_total_loss / sdf_test_loader.__len__()
        print('test_avrg_loss: {}\n'.format(test_avrg_loss))

        # 写入测试结果
        test_split_ = test_split.replace("/", "-").replace("\\", "-")
        model_ = model.replace("/", "-").replace("\\", "-")
        test_result_filename = os.path.join(test_result_dir, "{}+{}.txt".format(test_split_, model_))
        with open(test_result_filename, 'w') as f:
            f.write("test_split: {}\n".format(test_split))
            f.write("model: {}\n".format(model))
            f.write("avrg_loss: {}\n".format(test_avrg_loss))


def main_function(experiment_config_file, model):
    specs = ws.load_experiment_specifications(experiment_config_file)
    device = specs["Device"]

    sdf_loader = get_dataloader(specs)
    # 读取模型
    IBS_Net = torch.load(model, map_location="cuda:{}".format(device))
    # 测试并返回loss
    test(IBS_Net, sdf_loader, specs, model)


if __name__ == '__main__':
    import argparse

    arg_parser = argparse.ArgumentParser(description="Train a IBS Net")
    arg_parser.add_argument(
        "--experiment",
        "-e",
        dest="experiment_config_file",
        required=True,
        help="The experiment config file."
    )
    arg_parser.add_argument(
        "--model",
        "-m",
        dest="model",
        required=True,
        help="Whether visualization is needed."
    )
    args = arg_parser.parse_args()

    main_function(args.experiment_config_file, args.model)
