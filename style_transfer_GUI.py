import os
import copy
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms as transforms
#Changes made between short to long segments of ####
#Some things say Deleted:
from PIL import Image
from CaffeLoader import loadCaffemodel, ModelParallel

from gooey import Gooey, GooeyParser

@Gooey(default_size=(1280, 720))
def gpu():
    parser = GooeyParser(description = "Style Transfer GUI")
    # Basic options
    parser.add_argument("content_image", help="Desired content image.", widget = "FileChooser")
    parser.add_argument("style_image", help="Desired style image. If multiple are chosen, make sure they are separated by a , and not a ;", widget = "MultiFileChooser")
    parser.add_argument("image_size", help="Maximum height/width of generated image.", type=int, default=384)
    parser.add_argument("output_image", help ="The name you wish to save to, make sure to inlude the .jpg extension.", default='output/')
    parser.add_argument("-cudnn_autotune", help ="Do you want to use cudnn_autotune?", action='store_true', default = True)
    parser.add_argument("-init_image", help="Desired initialization image.", widget = "FileChooser", default=None)
    parser.add_argument("original_colors", help ="Do you want to use the content's original colors?", type=int, choices=[0, 1], default=0)
    parser.add_argument("-gpu", help="Zero-indexed ID of the GPU to use; for CPU mode set gpu = c.", default=0)

    # Optimization options
    parser.add_argument("content_weight", help ="The weight of the content image.", type=float, default=5)
    parser.add_argument("style_weight", help ="The weight of the style image.", type=float, default=1000)
    parser.add_argument("-style_blend_weights", help = "The weights when using multiple styles.", default=None)
    parser.add_argument("tv_weight", help ="Setting this low will make the final image more crisp.", type=float, default=0.00085)
    parser.add_argument("num_iterations", help ="Number of iterations to run.", type=int, default=1000)
    parser.add_argument("-init", help ="Intialize an image or something random?", choices=['random', 'image'], default='image')
    parser.add_argument("-optimizer", help ="LBFGS is better, but uses more memory than Adam.", choices=['lbfgs', 'adam'], default='lbfgs')
    parser.add_argument("-learning_rate", help ="The learning rate for when using Adam.", type=float, default=1e0)
    parser.add_argument("-lbfgs_num_correction",help ="Literally no idea what this does.", type=int, default=100)

    # Output options
    parser.add_argument("print_iter",help ="How often do you want to be updated on the progess?", type=int, default=50)
    parser.add_argument("save_iter",help ="How often do you want to save the created image?", type=int, default='0')

    # Other options
    parser.add_argument("-style_scale",help ="At what scale to get features from style image.", type=float, default=1.0)
    parser.add_argument("-pooling", help ="You can change this, but I prefer max over avg.", choices=['avg', 'max'], default='max')
    parser.add_argument("-model_file",help ="Path to the .pth VGG Caffe model.", type=str, default='models/vgg19-d01eb7cb.pth')
    parser.add_argument("-disable_check",help ="No clue.", action='store_true')
    parser.add_argument("-backend",help ="I like cudnn, but I believe that for CPU you have to use nn never tested myself.", choices=['nn', 'cudnn', 'mkl', 'mkldnn', 'openmp', 'mkl,cudnn', 'cudnn,mkl'], default='cudnn')
    parser.add_argument("-normalize_weights",help ="Not really sure, I've tried it and did not like the resutls.", action='store_true')
    parser.add_argument("-seed",help ="Random seed.", type=int, default=100)
    parser.add_argument("-content_layers", help="Layers to use from the content image. The defaults I have set work really well.", default='relu1_1,relu2_1,relu3_1,relu4_1,relu4_2,relu5_1')
    parser.add_argument("-style_layers", help="Layers to use from the style image. The defaults I have set work really well.", default='relu3_1,relu4_1,relu4_2,relu5_1')

    parser.add_argument("-multidevice_strategy",help="If you're rich and have more than one GPU. No idea how to use this option.", default='4,7,29')
    params = parser.parse_args()
    return params

    Image.MAX_IMAGE_PIXELS = 1000000000 # Support gigapixel images



def main():
    dtype, multidevice, backward_device = setup_gpu()

    cnn, layerList = loadCaffemodel(params.model_file, params.pooling, params.gpu, params.disable_check)

    content_image = preprocess(params.content_image, params.image_size).type(dtype)


    #####################################################
    Ch = content_image.size(2) #literally no idea why its (2) and not [0]
    Cw = content_image.size(3) #literally no idea why its (3) and not [1]
    #################################################################
    
    style_image_input = params.style_image.split(',')
    style_image_list, ext = [], [".jpg", ".jpeg", ".png", ".tiff"]
    for image in style_image_input:
        if os.path.isdir(image):
            images = (image + "/" + file for file in os.listdir(image)
            if os.path.splitext(file)[1].lower() in ext)
            style_image_list.extend(images)
        else:
            style_image_list.append(image)
    style_images_caffe = []
    for image in style_image_list:
        #################################################
        image_path = image
        print(image_path)
        im_sizing = Image.open(image_path)
        print(im_sizing)
        Sh = im_sizing.size[0] #this one is the way I expect it to be, but the Ch is not
        Sw = im_sizing.size[1] #this one is the way I expect it to be, but the Ch is not
        style_size = 0
        resizeStyle = 1
        Cr = Cw / Ch
        Sr = Sw / Sh

        if Cr >= Sr:
            if Sr >= 1:
                style_size = Cw * params.style_scale
            else:
                style_size = params.style_scale * Cw * Sh /Sw

            if style_size > Sw:
                style_size = Sw
                resizeStyle = 0
        else:
            if Sr >= 1:
                style_size = params.style_scale * Ch * Sw /Sh
            else:
                style_size = Ch * params.style_scale

            if style_size > Sh:
                style_size = Sh
                resizeStyle = 0
        
        #############################################################
        #Deleted: style_size = int(params.image_size * params.style_scale)
        
        img_caffe = preprocess(image, style_size).type(dtype)
        style_images_caffe.append(img_caffe)

    if params.init_image != None:
        image_size = (content_image.size(2), content_image.size(3))
        init_image = preprocess(params.init_image, image_size).type(dtype)

    # Handle style blending weights for multiple style inputs
    style_blend_weights = []
    if params.style_blend_weights == None:
        # Style blending not specified, so use equal weighting
        for i in style_image_list:
            style_blend_weights.append(1.0)
        for i, blend_weights in enumerate(style_blend_weights):
            style_blend_weights[i] = int(style_blend_weights[i])
    else:
        style_blend_weights = params.style_blend_weights.split(',')
        assert len(style_blend_weights) == len(style_image_list), \
          "-style_blend_weights and -style_images must have the same number of elements!"

    # Normalize the style blending weights so they sum to 1
    style_blend_sum = 0
    for i, blend_weights in enumerate(style_blend_weights):
        style_blend_weights[i] = float(style_blend_weights[i])
        style_blend_sum = float(style_blend_sum) + style_blend_weights[i]
    for i, blend_weights in enumerate(style_blend_weights):
        style_blend_weights[i] = float(style_blend_weights[i]) / float(style_blend_sum)

    content_layers = params.content_layers.split(',')
    style_layers = params.style_layers.split(',')

    # Set up the network, inserting style and content loss modules
    cnn = copy.deepcopy(cnn)
    content_losses, style_losses, tv_losses = [], [], []
    next_content_idx, next_style_idx = 1, 1
    net = nn.Sequential()
    c, r = 0, 0
    if params.tv_weight > 0:
        tv_mod = TVLoss(params.tv_weight).type(dtype)
        net.add_module(str(len(net)), tv_mod)
        tv_losses.append(tv_mod)

    for i, layer in enumerate(list(cnn), 1):
        if next_content_idx <= len(content_layers) or next_style_idx <= len(style_layers):
            if isinstance(layer, nn.Conv2d):
                net.add_module(str(len(net)), layer)

                if layerList['C'][c] in content_layers:
                    print("Setting up content layer " + str(i) + ": " + str(layerList['C'][c]))
                    loss_module = ContentLoss(params.content_weight)
                    net.add_module(str(len(net)), loss_module)
                    content_losses.append(loss_module)

                if layerList['C'][c] in style_layers:
                    print("Setting up style layer " + str(i) + ": " + str(layerList['C'][c]))
                    loss_module = StyleLoss(params.style_weight)
                    net.add_module(str(len(net)), loss_module)
                    style_losses.append(loss_module)
                c+=1

            if isinstance(layer, nn.ReLU):
                net.add_module(str(len(net)), layer)

                if layerList['R'][r] in content_layers:
                    print("Setting up content layer " + str(i) + ": " + str(layerList['R'][r]))
                    loss_module = ContentLoss(params.content_weight)
                    net.add_module(str(len(net)), loss_module)
                    content_losses.append(loss_module)
                    next_content_idx += 1

                if layerList['R'][r] in style_layers:
                    print("Setting up style layer " + str(i) + ": " + str(layerList['R'][r]))
                    loss_module = StyleLoss(params.style_weight)
                    net.add_module(str(len(net)), loss_module)
                    style_losses.append(loss_module)
                    next_style_idx += 1
                r+=1

            if isinstance(layer, nn.MaxPool2d) or isinstance(layer, nn.AvgPool2d):
                net.add_module(str(len(net)), layer)

    if multidevice:
        net = setup_multi_device(net)

    # Capture content targets
    for i in content_losses:
        i.mode = 'capture'
    print("Capturing content targets")
    print_torch(net, multidevice)
    net(content_image)

    # Capture style targets
    for i in content_losses:
        i.mode = 'None'

    for i, image in enumerate(style_images_caffe):
        print("Capturing style target " + str(i+1))
        for j in style_losses:
            j.mode = 'capture'
            j.blend_weight = style_blend_weights[i]
        net(style_images_caffe[i])

    # Set all loss modules to loss mode
    for i in content_losses:
        i.mode = 'loss'
    for i in style_losses:
        i.mode = 'loss'

    # Maybe normalize content and style weights
    if params.normalize_weights:
        normalize_weights(content_losses, style_losses)

    # Freeze the network in order to prevent
    # unnecessary gradient calculations
    for param in net.parameters():
        param.requires_grad = False

    # Initialize the image
    if params.seed >= 0:
        torch.manual_seed(params.seed)
        torch.cuda.manual_seed_all(params.seed)
        torch.backends.cudnn.deterministic=True
    if params.init == 'random':
        B, C, H, W = content_image.size()
        img = torch.randn(C, H, W).mul(0.001).unsqueeze(0).type(dtype)
    elif params.init == 'image':
        if params.init_image != None:
            img = init_image.clone()
        else:
            img = content_image.clone()
    img = nn.Parameter(img)

    def maybe_print(t, loss):
        if params.print_iter > 0 and t % params.print_iter == 0:
            print("Iteration " + str(t) + " / "+ str(params.num_iterations))
            for i, loss_module in enumerate(content_losses):
                print("  Content " + str(i+1) + " loss: " + str(loss_module.loss.item()))
            for i, loss_module in enumerate(style_losses):
                print("  Style " + str(i+1) + " loss: " + str(loss_module.loss.item()))
            print("  Total loss: " + str(loss.item()))

    def maybe_save(t):
        should_save = params.save_iter > 0 and t % params.save_iter == 0
        should_save = should_save or t == params.num_iterations
        if should_save:
            output_filename, file_extension = os.path.splitext(params.output_image)
            if t == params.num_iterations:
                filename = output_filename + str(file_extension)
            else:
                filename = str(output_filename) + "_" + str(t) + str(file_extension)
            disp = deprocess(img.clone())

            # Maybe perform postprocessing for color-independent style transfer
            if params.original_colors == 1:
                disp = original_colors(deprocess(content_image.clone()), disp)

            disp.save(str(filename))

    # Function to evaluate loss and gradient. We run the net forward and
    # backward to get the gradient, and sum up losses from the loss modules.
    # optim.lbfgs internally handles iteration and calls this function many
    # times, so we manually count the number of iterations to handle printing
    # and saving intermediate results.
    num_calls = [0]
    def feval():
        num_calls[0] += 1
        optimizer.zero_grad()
        net(img)
        loss = 0

        for mod in content_losses:
            loss += mod.loss.to(backward_device)
        for mod in style_losses:
            loss += mod.loss.to(backward_device)
        if params.tv_weight > 0:
            for mod in tv_losses:
                loss += mod.loss.to(backward_device)

        loss.backward()

        maybe_save(num_calls[0])
        maybe_print(num_calls[0], loss)

        return loss

    optimizer, loopVal = setup_optimizer(img)
    while num_calls[0] <= loopVal:
         optimizer.step(feval)


# Configure the optimizer
def setup_optimizer(img):
    if params.optimizer == 'lbfgs':
        print("Running optimization with L-BFGS")
        optim_state = {
            'max_iter': params.num_iterations,
            'tolerance_change': -1,
            'tolerance_grad': -1,
        }
        if params.lbfgs_num_correction != 100:
            optim_state['history_size'] = params.lbfgs_num_correction
        optimizer = optim.LBFGS([img], **optim_state)
        loopVal = 1
    elif params.optimizer == 'adam':
        print("Running optimization with ADAM")
        optimizer = optim.Adam([img], lr = params.learning_rate)
        loopVal = params.num_iterations - 1
    return optimizer, loopVal


def setup_gpu():
    def setup_cuda():
        if 'cudnn' in params.backend:
            torch.backends.cudnn.enabled = True
            if params.cudnn_autotune:
                torch.backends.cudnn.benchmark = True
        else:
            torch.backends.cudnn.enabled = False

    def setup_cpu():
        if 'mkl' in params.backend and 'mkldnn' not in params.backend:
            torch.backends.mkl.enabled = True
        elif 'mkldnn' in params.backend:
            raise ValueError("MKL-DNN is not supported yet.")
        elif 'openmp' in params.backend:
            torch.backends.openmp.enabled = True

    multidevice = False
    if "," in str(params.gpu):
        devices = params.gpu.split(',')
        multidevice = True

        if 'c' in str(devices[0]).lower():
            backward_device = "cpu"
            setup_cuda(), setup_cpu()
        else:
            backward_device = "cuda:" + devices[0]
            setup_cuda()
        dtype = torch.FloatTensor

    elif "c" not in str(params.gpu).lower():
        setup_cuda()
        dtype, backward_device = torch.cuda.FloatTensor, "cuda:" + str(params.gpu)
    else:
        setup_cpu()
        dtype, backward_device = torch.FloatTensor, "cpu"
    return dtype, multidevice, backward_device


def setup_multi_device(net):
    assert len(params.gpu.split(',')) - 1 == len(params.multidevice_strategy.split(',')), \
      "The number of -multidevice_strategy layer indices minus 1, must be equal to the number of -gpu devices."

    new_net = ModelParallel(net, params.gpu, params.multidevice_strategy)
    return new_net


# Preprocess an image before passing it to a model.
# We need to rescale from [0, 1] to [0, 255], convert from RGB to BGR,
# and subtract the mean pixel.
def preprocess(image_name, image_size):
    image = Image.open(image_name).convert('RGB')
    if type(image_size) is not tuple:
        image_size = tuple([int((float(image_size) / max(image.size))*x) for x in (image.height, image.width)])
    Loader = transforms.Compose([transforms.Resize(image_size), transforms.ToTensor()])
    rgb2bgr = transforms.Compose([transforms.Lambda(lambda x: x[torch.LongTensor([2,1,0])])])
    Normalize = transforms.Compose([transforms.Normalize(mean=[103.939, 116.779, 123.68], std=[1,1,1])])
    tensor = Normalize(rgb2bgr(Loader(image) * 256)).unsqueeze(0)
    return tensor


#  Undo the above preprocessing.
def deprocess(output_tensor):
    Normalize = transforms.Compose([transforms.Normalize(mean=[-103.939, -116.779, -123.68], std=[1,1,1])])
    bgr2rgb = transforms.Compose([transforms.Lambda(lambda x: x[torch.LongTensor([2,1,0])])])
    output_tensor = bgr2rgb(Normalize(output_tensor.squeeze(0).cpu())) / 256
    output_tensor.clamp_(0, 1)
    Image2PIL = transforms.ToPILImage()
    image = Image2PIL(output_tensor.cpu())
    return image


# Combine the Y channel of the generated image and the UV/CbCr channels of the
# content image to perform color-independent style transfer.
def original_colors(content, generated):
    content_channels = list(content.convert('YCbCr').split())
    generated_channels = list(generated.convert('YCbCr').split())
    content_channels[0] = generated_channels[0]
    return Image.merge('YCbCr', content_channels).convert('RGB')


# Print like Lua/Torch7
def print_torch(net, multidevice):
    if multidevice:
        return
    simplelist = ""
    for i, layer in enumerate(net, 1):
        simplelist = simplelist + "(" + str(i) + ") -> "
    print("nn.Sequential ( \n  [input -> " + simplelist + "output]")

    def strip(x):
        return str(x).replace(", ",',').replace("(",'').replace(")",'') + ", "
    def n():
        return "  (" + str(i) + "): " + "nn." + str(l).split("(", 1)[0]

    for i, l in enumerate(net, 1):
         if "2d" in str(l):
             ks, st, pd = strip(l.kernel_size), strip(l.stride), strip(l.padding)
             if "Conv2d" in str(l):
                 ch = str(l.in_channels) + " -> " + str(l.out_channels)
                 print(n() + "(" + ch + ", " + (ks).replace(",",'x', 1) + st + pd.replace(", ",')'))
             elif "Pool2d" in str(l):
                 st = st.replace("  ",' ') + st.replace(", ",')')
                 print(n() + "(" + ((ks).replace(",",'x' + ks, 1) + st).replace(", ",','))
         else:
             print(n())
    print(")")


# Divide weights by channel size
def normalize_weights(content_losses, style_losses):
    for n, i in enumerate(content_losses):
        i.strength = i.strength / max(i.target.size())
    for n, i in enumerate(style_losses):
        i.strength = i.strength / max(i.target.size())


# Define an nn Module to compute content loss
class ContentLoss(nn.Module):

    def __init__(self, strength):
        super(ContentLoss, self).__init__()
        self.strength = strength
        self.crit = nn.MSELoss()
        self.mode = 'None'

    def forward(self, input):
        if self.mode == 'loss':
            self.loss = self.crit(input, self.target) * self.strength
        elif self.mode == 'capture':
            self.target = input.detach()
        return input


class GramMatrix(nn.Module):

    def forward(self, input):
        B, C, H, W = input.size()
        x_flat = input.view(C, H * W)
        return torch.mm(x_flat, x_flat.t())


# Define an nn Module to compute style loss
class StyleLoss(nn.Module):

    def __init__(self, strength):
        super(StyleLoss, self).__init__()
        self.target = torch.Tensor()
        self.strength = strength
        self.gram = GramMatrix()
        self.crit = nn.MSELoss()
        self.mode = 'None'
        self.blend_weight = None

    def forward(self, input):
        self.G = self.gram(input)
        self.G = self.G.div(input.nelement())
        if self.mode == 'capture':
            if self.blend_weight == None:
                self.target = self.G.detach()
            elif self.target.nelement() == 0:
                self.target = self.G.detach().mul(self.blend_weight)
            else:
                self.target = self.target.add(self.blend_weight, self.G.detach())
        elif self.mode == 'loss':
            self.loss = self.strength * self.crit(self.G, self.target)
        return input


class TVLoss(nn.Module):

    def __init__(self, strength):
        super(TVLoss, self).__init__()
        self.strength = strength

    def forward(self, input):
        self.x_diff = input[:,:,1:,:] - input[:,:,:-1,:]
        self.y_diff = input[:,:,:,1:] - input[:,:,:,:-1]
        self.loss = self.strength * (torch.sum(torch.abs(self.x_diff)) + torch.sum(torch.abs(self.y_diff)))
        return input


if __name__ == "__main__":
    params = gpu()
    main()
