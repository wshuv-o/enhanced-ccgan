import torch
print(torch.__version__)  # Should print the version you installed, e.g., 1.12.0
print(torch.cuda.is_available())  # Should print True if CUDA is properly installed
import torchvision
print(torchvision.__version__)  # Should print the version you installed, e.g., 0.13.0

import numpy as np

print(np.__version__)
