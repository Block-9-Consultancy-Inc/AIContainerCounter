from torchvision import transforms, models
import torchvision.transforms.functional as F
import numpy as np
from PIL.Image import Image
import torch

class NumpyToTensor:
	def __call__(self, image):
		tensor = torch.from_numpy(image)
		tensor = tensor.permute((2, 0, 1)).contiguous()
		return tensor

class SquarePad:
	def __call__(self, image):
		if isinstance(image, Image):
			w, h = image.size
		else:
			_, h, w = image.shape
		max_wh = np.max([w, h])
		hp = int((max_wh - w) / 2)
		vp = int((max_wh - h) / 2)
		padding = (hp, vp, hp, vp)
		return F.pad(image, padding, 0, 'constant')
	
def square_pad_numpy_transform(image_size: int):
	return transforms.Compose([
		NumpyToTensor(),
        SquarePad(),
        transforms.Resize(image_size),
        transforms.CenterCrop(image_size),
		transforms.Lambda(lambda e: e.to(dtype=torch.get_default_dtype())),
        transforms.Normalize((127.5, 127.5, 127.5), (127.5, 127.5, 127.5)),
    ])

class CategoryClassifier:
	def __init__(self, model_path: str):
		self.transform = square_pad_numpy_transform(224)
		self.model = models.resnet18()
		self.model.fc = torch.nn.Linear(self.model.fc.in_features, 5)
		self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
		self.model.to(self.device)
		self.model.load_state_dict(torch.load(model_path))
		self.model.eval()
		
	def run_inference(self, images: list[np.ndarray]):
		transformed_images = np.array(list(map(lambda e: self.transform(e), images)))
		tensors = torch.tensor(transformed_images).to(self.device)
		with torch.no_grad():
			outputs = self.model(tensors)
			_, predicted = torch.max(outputs, 1)
		
		predicted_array = predicted.cpu().numpy()
		return predicted_array
	