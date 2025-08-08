import argparse
import os
import torch
import numpy as np
import os

from model import RecurrentStylization
from postprocess import remove_fs
from utils.animation_data import AnimationData

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

content_labels = ["walk", "run", "jump", "punch", "kick"]
style_labels = ["angry", "childlike", "depressed", "old", "proud", "sexy", "strutting"]

class ArgParserTest(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # setup hyperparameters
        self.add_argument('--content_num', type=int, default=5)
        self.add_argument('--style_num', type=int, default=7)
        self.add_argument('--episode_length', type=int, default=24)
        self.add_argument("--data_path", default='./data/xia.npz')
        self.add_argument("--work_dir", default='./experiments/')
        self.add_argument("--load_dir", default=None, type=str)
        self.add_argument("--input_motion", default=None, type=str)
        self.add_argument("--input_content", default=None, type=str)
        self.add_argument("--input_style", default=None, type=str)
        self.add_argument("--target_style", default=None, type=str)        

        # model hyperparameters
        self.add_argument("--no_pos", default=False, action='store_true')
        self.add_argument("--no_vel", default=False, action='store_true')
        self.add_argument("--encoder_layer_num", type=int, default=2)
        self.add_argument("--decoder_layer_num", type=int, default=4)
        self.add_argument("--discriminator_layer_num", type=int, default=4)
        self.add_argument("--classifier_layer_num", type=int, default=5)
        self.add_argument("--latent_dim", type=int, default=32)
        self.add_argument("--neutral_layer_num", type=int, default=4)
        self.add_argument("--style_layer_num", type=int, default=6)
        self.add_argument("--feature_dim", type=int, default=16)

def process_single_bvh(filename, args, downsample=4, skel=None):

    anim = AnimationData.from_BVH(filename, downsample=downsample, skel=skel, trim_scale=4)

    episode_length = anim.len
    style_array = np.zeros(len(style_labels))
    if args.input_style != "neutral":
        style_array[style_labels.index(args.input_style)] = 1.0

    target_style = np.zeros(len(style_labels))
    if args.target_style != "neutral":
        target_style[style_labels.index(args.target_style)] = 1.0
    content_index = content_labels.index(args.input_content)
    data = {
            "rotation": torch.FloatTensor(anim.get_joint_rotation()).to(device),
            "position": torch.FloatTensor(anim.get_joint_position()).to(device),
            "velocity": torch.FloatTensor(anim.get_joint_velocity()).to(device),
            "content": torch.FloatTensor(np.tile([np.eye(len(content_labels))[content_index]],(episode_length, 1))).to(device),
            "contact": torch.FloatTensor(anim.get_foot_contact(transpose=False)).to(device),
            "root": torch.FloatTensor(anim.get_root_posrot()).to(device),
            "input_style": torch.FloatTensor(np.tile([style_array],(episode_length,1))).to(device),
            "transferred_style": torch.FloatTensor(np.tile([target_style],(episode_length,1))).to(device),
            "content_index": torch.LongTensor(content_index).to(device)
        }
    
    dim_dict = {
            "rotation": data["rotation"][0].shape[-1],
            "position": data["position"][0].shape[-1],
            "velocity": data["velocity"][0].shape[-1],
            "style": len(style_labels), 
            "content": len(content_labels),
            "contact": data["contact"][0].shape[-1],
            "root": data["root"][0].shape[-1]
        }

    return data, dim_dict

def main():
    args = ArgParserTest().parse_args()
    
    test_data, dim_dict = process_single_bvh(args.input_motion, args, downsample=2)

    model = RecurrentStylization(args, dim_dict).to(device)

    model.load_state_dict(torch.load(os.path.join(args.load_dir, 'model/model_2000.pt'), map_location=device)) 
    model.eval()

    for (key,val) in test_data.items():
        if key != "content_index":
            test_data[key] = val.unsqueeze(0)
    

    content = args.input_content
    input_style = args.input_style
    output_style = args.target_style

    transferred_motion = model.forward_gen(test_data["rotation"], test_data["position"], test_data["velocity"],
                        test_data["content"], test_data["contact"],
                        test_data["input_style"], test_data["transferred_style"], test_time=True)
    
    transferred_motion = transferred_motion["rotation"].squeeze(0)
    root_info = test_data["root"].squeeze(0).transpose(0, 1)
    foot_contact = test_data["contact"].cpu().squeeze(0).transpose(0, 1).numpy()
    transferred_motion = torch.cat((transferred_motion,root_info), dim=-1).transpose(0, 1).detach().cpu()
    remove_fs(
        transferred_motion,
        foot_contact,
        output_path="output_dir/{}_to_{}_{}.bvh".format(input_style, output_style, content)
    )


if __name__ == "__main__":
    main()