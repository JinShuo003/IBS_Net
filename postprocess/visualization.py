"""
可视化工具，配置好./config/visualization.json后可以可视化mesh模型、点云、位于模型表面和IBS表面的sdf点、各自和总体的aabb框、交互区域gt
"""
import open3d as o3d
import os
import re
import json
import numpy as np
import copy
from utils.path_utils import getFilenameTree


def parseConfig(config_filepath: str = './config/visualization.json'):
    with open(config_filepath, 'r') as configfile:
        specs = json.load(configfile)

    return specs


# def getFilenameTree(specs: dict, base_path):
#     # 以SDF GT作为基准构建文件树
#     category_re = specs["category_re"]
#     scene_re = specs["scene_re"]
#     filename_re = specs["filename_re"]
#
#     filename_tree = dict()
#     folder_info = os.walk(base_path)
#     for dir_path, dir_names, filenames in folder_info:
#         # 当前是顶级目录，不做处理
#         if dir_path == base_path:
#             continue
#         # 获取当前文件夹的类目信息，合法则继续处理
#         category = dir_path.split('\\')[-1]
#         if not re.match(category_re, category):
#             continue
#         # 当前类目不在filename_tree中，添加
#         if not category in filename_tree:
#             filename_tree[category] = dict()
#         for filename in filenames:
#             if not re.match(filename_re, filename):
#                 continue
#             # 获取场景名
#             scene = re.match(scene_re, filename)
#             # 如果与场景re不匹配则跳过
#             if not scene:
#                 continue
#             scene = scene.group()
#             # 当前场景不在filename_tree[category]中，添加
#             if not scene in filename_tree[category]:
#                 filename_tree[category][scene] = list()
#             filename_tree[category][scene].append(filename)
#
#     return filename_tree


def getGeometryPath(specs, filename):
    scene_re = specs["scene_re"]
    category_re = specs["category_re"]
    filename_re = specs["filename_re"]
    category = re.match(category_re, filename).group()
    scene = re.match(scene_re, filename).group()
    filename = re.match(filename_re, filename).group()

    geometry_path = dict()

    mesh_dir = specs['mesh_dir']
    ibs_mesh_gt_dir = specs['ibs_mesh_gt_dir']
    ibs_mesh_pred_dir = specs['ibs_mesh_pred_dir']
    ibs_pcd_gt_dir = specs['ibs_pcd_gt_dir']
    ibs_pcd_pred_dir = specs['ibs_pcd_pred_dir']
    pcd_dir = specs['pcd_dir']
    sdf_complete_pred_dir = specs['sdf_complete_pred_dir']
    sdf_complete_gt_dir = specs['sdf_complete_gt_dir']
    sdf_direct_pred_dir = specs['sdf_direct_pred_dir']
    sdf_direct_gt_dir = specs['sdf_direct_gt_dir']
    sdf_partial_dir = specs['sdf_partial_dir']
    IOU_dir = specs['IOUgt_dir']

    mesh1_filename = '{}_{}.obj'.format(scene, 0)
    mesh2_filename = '{}_{}.obj'.format(scene, 1)
    ibs_mesh_gt_filename = '{}.obj'.format(scene)
    ibs_mesh_pred_filename = '{}.obj'.format(filename)
    ibs_pcd_gt_filename = '{}.ply'.format(scene)
    ibs_pcd_pred_filename = '{}.ply'.format(filename)
    pcd1_filename = '{}_{}.ply'.format(filename, 0)
    pcd2_filename = '{}_{}.ply'.format(filename, 1)
    sdf_filename = '{}.npz'.format(filename)
    IOU_filename = '{}.npy'.format(scene)

    geometry_path['mesh1'] = os.path.join(mesh_dir, category, mesh1_filename)
    geometry_path['mesh2'] = os.path.join(mesh_dir, category, mesh2_filename)
    geometry_path['ibs_mesh_gt'] = os.path.join(ibs_mesh_gt_dir, category, ibs_mesh_gt_filename)
    geometry_path['ibs_mesh_pred'] = os.path.join(ibs_mesh_pred_dir, category, ibs_mesh_pred_filename)
    geometry_path['ibs_pcd_gt'] = os.path.join(ibs_pcd_gt_dir, category, ibs_pcd_gt_filename)
    geometry_path['ibs_pcd_pred'] = os.path.join(ibs_pcd_pred_dir, category, ibs_pcd_pred_filename)
    geometry_path['pcd1'] = os.path.join(pcd_dir, category, pcd1_filename)
    geometry_path['pcd2'] = os.path.join(pcd_dir, category, pcd2_filename)
    geometry_path['ibs_complete_pred'] = os.path.join(sdf_complete_pred_dir, category, sdf_filename)
    geometry_path['ibs_complete_gt'] = os.path.join(sdf_complete_gt_dir, category, sdf_filename)
    geometry_path['ibs_direct_pred'] = os.path.join(sdf_direct_pred_dir, category, sdf_filename)
    geometry_path['ibs_direct_gt'] = os.path.join(sdf_direct_gt_dir, category, sdf_filename)
    geometry_path['ibs_partial'] = os.path.join(sdf_partial_dir, category, sdf_filename)
    geometry_path['IOU'] = os.path.join(IOU_dir, category, IOU_filename)

    return geometry_path


def getGeometryColor(specs):
    geometry_color_dict = specs["visualization_options"]["colors"]
    for key in geometry_color_dict.keys():
        geometry_color_dict[key] = tuple(geometry_color_dict[key])
    return geometry_color_dict


def getGeometryOption(specs):
    geometry_color_dict = specs["visualization_options"]["geometries"]
    return geometry_color_dict


def combine_meshes(mesh1, mesh2):
    if mesh1 is None or mesh2 is None:
        return None
    # 获取第一个Mesh的顶点和面数据
    vertices1 = mesh1.vertices
    faces1 = np.asarray(mesh1.triangles)

    # 获取第二个Mesh的顶点和面数据
    vertices2 = mesh2.vertices
    faces2 = np.asarray(mesh2.triangles)

    # 将第二个Mesh的顶点坐标添加到第一个Mesh的顶点列表中
    combined_vertices = np.concatenate((vertices1, vertices2))

    # 更新第二个Mesh的面索引，使其适应顶点索引的变化
    faces2 += len(vertices1)

    # 将两个Mesh的面数据合并
    combined_faces = np.concatenate((faces1, faces2))

    # 创建一个新的Mesh对象
    combined_mesh = o3d.geometry.TriangleMesh()

    # 设置新的Mesh的顶点和面数据
    combined_mesh.vertices = o3d.utility.Vector3dVector(combined_vertices)
    combined_mesh.triangles = o3d.utility.Vector3iVector(combined_faces)

    return combined_mesh


def get_unit_sphere_pcd():
    mesh_sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.5)
    pcd = mesh_sphere.sample_points_uniformly(256)
    return pcd


def get_coordinate():
    return o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0)


class meshGetter:
    def __init__(self):
        pass

    def read_mesh(self, mesh_path):
        return o3d.io.read_triangle_mesh(mesh_path)

    def colour_mesh(self, mesh, mesh_color):
        mesh.paint_uniform_color(mesh_color)

    def get_mesh(self, *args):
        """kwargs: """
        mesh_path = args[0]
        mesh_color = args[1]
        mesh_option = args[2]
        aabb_total_option = args[3] if len(args) == 4 else True

        if mesh_option is False and aabb_total_option is False:
            return None
        mesh = self.read_mesh(mesh_path)
        self.colour_mesh(mesh, mesh_color)
        return mesh


class aabbGetter:
    def __init__(self):
        pass

    def get_aabb_from_mesh(self, mesh):
        return mesh.get_axis_aligned_bounding_box()

    def colour_mesh(self, aabb, aabb_color):
        aabb.color = aabb_color

    def get_aabb(self, mesh, aabb_color, aabb_option):
        if aabb_option is not True:
            return None
        aabb = self.get_aabb_from_mesh(mesh)
        self.colour_mesh(aabb, aabb_color)
        return aabb


class pcdGetter:
    def __init__(self):
        pass

    def read_pcd(self, pcd_path):
        return o3d.io.read_point_cloud(pcd_path)

    def colour_pcd(self, pcd, pcd_color):
        pcd.paint_uniform_color(pcd_color)

    def get_pcd(self, pcd_path, pcd_color, pcd_option):
        if pcd_option is not True:
            return None
        pcd = self.read_pcd(pcd_path)
        self.colour_pcd(pcd, pcd_color)
        pcd.normals = o3d.utility.Vector3dVector([])
        return pcd


class ibsSurfaceGetter:
    def __init__(self):
        pass

    def read_ibs_pcd(self, sdf_path, type):
        npz = np.load(sdf_path)
        data = npz["data"]
        if type == "indirect":
            surface_points_ibs = [points[0:3] for points in data if
                                  abs(points[3] - points[4]) < specs['visualization_options']['sdf_threshold']]
        elif type == "direct":
            surface_points_ibs = [points[0:3] for points in data if
                                  points[3] < specs['visualization_options']['sdf_threshold']]
        else:
            raise TypeError
        ibs_pcd = o3d.geometry.PointCloud()
        ibs_pcd.points = o3d.utility.Vector3dVector(surface_points_ibs)
        return ibs_pcd

    def colour_ibs_pcd(self, ibs_pcd, ibs_pcd_color):
        ibs_pcd.paint_uniform_color(ibs_pcd_color)

    def get_ibs_pcd(self, sdf_path, ibs_pcd_color, ibs_pcd_option, type):
        if ibs_pcd_option is not True:
            return None
        ibs_pcd = self.read_ibs_pcd(sdf_path, type)
        # cl, ind = ibs_pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=1.0)
        # 根据索引提取滤波后的点云
        # ibs_pcd = ibs_pcd.select_by_index(ind)
        self.colour_ibs_pcd(ibs_pcd, ibs_pcd_color)
        return ibs_pcd


class IOUGetter:
    def __init__(self):
        pass

    def read_IOU(self, IOU_path):
        """获取交互区域的aabb框"""
        aabb_data = np.load(IOU_path)
        min_bound = aabb_data[0]
        max_bound = aabb_data[1]
        IOUgt = o3d.geometry.AxisAlignedBoundingBox(min_bound, max_bound)
        return IOUgt

    def colour_IOU(self, IOU, IOU_color):
        IOU.color = IOU_color

    def get_IOU(self, IOU_path, IOU_color, IOU_option):
        if IOU_option is not True:
            return None
        IOU = self.read_IOU(IOU_path)
        self.colour_IOU(IOU, IOU_color)
        return IOU


def visualize(specs, filename):
    container = dict()
    geometries = []
    geometry_path = getGeometryPath(specs, filename)
    geometry_color = getGeometryColor(specs)
    geometry_option = getGeometryOption(specs)

    mesh1 = meshGetter().get_mesh(geometry_path["mesh1"], geometry_color["mesh1"], geometry_option["mesh1"],
                                  geometry_option["aabb_total"])
    mesh2 = meshGetter().get_mesh(geometry_path["mesh2"], geometry_color["mesh2"], geometry_option["mesh2"],
                                  geometry_option["aabb_total"])
    ibs_mesh_gt = meshGetter().get_mesh(geometry_path["ibs_mesh_gt"], geometry_color["ibs_mesh_gt"],
                                        geometry_option["ibs_mesh_gt"])
    ibs_mesh_pred = meshGetter().get_mesh(geometry_path["ibs_mesh_pred"], geometry_color["ibs_mesh_pred"],
                                          geometry_option["ibs_mesh_pred"])
    ibs_pcd_gt = pcdGetter().get_pcd(geometry_path["ibs_pcd_gt"], geometry_color["ibs_pcd_gt"],
                                     geometry_option["ibs_pcd_gt"])
    ibs_pcd_pred = pcdGetter().get_pcd(geometry_path["ibs_pcd_pred"], geometry_color["ibs_pcd_pred"],
                                       geometry_option["ibs_pcd_pred"])
    aabb1 = aabbGetter().get_aabb(mesh1, geometry_color["aabb1"], geometry_option["aabb1"])
    aabb2 = aabbGetter().get_aabb(mesh2, geometry_color["aabb2"], geometry_option["aabb2"])
    aabb_total = aabbGetter().get_aabb(combine_meshes(copy.deepcopy(mesh1), copy.deepcopy(mesh2)),
                                       geometry_color["aabb_total"], geometry_option["aabb_total"])
    IOU = IOUGetter().get_IOU(geometry_path['IOU'], geometry_color['IOU'], geometry_option["IOU"])
    pcd1 = pcdGetter().get_pcd(geometry_path['pcd1'], geometry_color['pcd1'], geometry_option["pcd1"])
    pcd2 = pcdGetter().get_pcd(geometry_path['pcd2'], geometry_color['pcd2'], geometry_option["pcd2"])
    ibs_complete_pred = ibsSurfaceGetter().get_ibs_pcd(geometry_path['ibs_complete_pred'],
                                                       geometry_color['ibs_complete_pred'],
                                                       geometry_option["ibs_complete_pred"], "indirect")
    ibs_complete_gt = ibsSurfaceGetter().get_ibs_pcd(geometry_path['ibs_complete_gt'],
                                                     geometry_color['ibs_complete_gt'],
                                                     geometry_option["ibs_complete_gt"], "indirect")
    ibs_direct_pred = ibsSurfaceGetter().get_ibs_pcd(geometry_path['ibs_direct_pred'],
                                                     geometry_color['ibs_direct_pred'],
                                                     geometry_option["ibs_direct_pred"], "direct")
    ibs_direct_gt = ibsSurfaceGetter().get_ibs_pcd(geometry_path['ibs_direct_gt'], geometry_color['ibs_direct_gt'],
                                                   geometry_option["ibs_direct_gt"], "direct")
    ibs_partial = ibsSurfaceGetter().get_ibs_pcd(geometry_path['ibs_partial'], geometry_color['ibs_partial'],
                                                 geometry_option["ibs_partial"], "indirect")
    coord_frame = get_coordinate()
    unit_sphere_pcd = get_unit_sphere_pcd()

    container['mesh1'] = mesh1
    container['mesh2'] = mesh2
    container['ibs_mesh_gt'] = ibs_mesh_gt
    container['ibs_mesh_pred'] = ibs_mesh_pred
    container['ibs_pcd_gt'] = ibs_pcd_gt
    container['ibs_pcd_pred'] = ibs_pcd_pred
    container['pcd1'] = pcd1
    container['pcd2'] = pcd2
    container['aabb1'] = aabb1
    container['aabb2'] = aabb2
    container['aabb_total'] = aabb_total
    container['IOU'] = IOU
    container['ibs_complete_pred'] = ibs_complete_pred
    container['ibs_complete_gt'] = ibs_complete_gt
    container['ibs_direct_pred'] = ibs_direct_pred
    container['ibs_direct_gt'] = ibs_direct_gt
    container['ibs_partial'] = ibs_partial
    container['coord_frame'] = coord_frame
    container['unit_sphere'] = unit_sphere_pcd

    for key in geometry_option.keys():
        if geometry_option[key] is True:
            geometries.append(container[key])

    o3d.visualization.draw_geometries(geometries, mesh_show_wireframe=True, mesh_show_back_face=True)


if __name__ == '__main__':
    # 获取配置参数
    config_filepath = 'config/visualization.json'
    specs = parseConfig(config_filepath)

    filename_tree = getFilenameTree(specs, specs["ibs_pcd_pred_dir"])

    for category in filename_tree:
        for scene in filename_tree[category]:
            print('current scene: ', scene)
            for filename in filename_tree[category][scene]:
                print('current file: ', filename)
                try:
                    visualize(specs, filename)
                except Exception:
                    pass
