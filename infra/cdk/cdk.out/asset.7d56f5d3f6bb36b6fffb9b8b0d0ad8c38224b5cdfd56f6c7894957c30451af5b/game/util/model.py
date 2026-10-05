import torch.nn as nn
import torch.nn.functional as F

from util.acceleration import accel_device



class ContinuousPolicyNetwork(nn.Module):
    def __init__(
        self,
        input_size=4,
        hidden_size=64,
        output_size=2,
        hidden_layers=4,
        device=None,
    ):
        super(ContinuousPolicyNetwork, self).__init__()
        if hidden_layers not in (2, 4):
            raise ValueError("hidden_layers must be 2 or 4")

        gpu = accel_device() if device is None else device
        self.fc1 = nn.Linear(input_size, hidden_size, device=gpu)
        self.fc2 = nn.Linear(hidden_size, hidden_size, device=gpu)
        if hidden_layers == 4:
            self.fc3 = nn.Linear(hidden_size, hidden_size, device=gpu)
            self.fc4 = nn.Linear(hidden_size, hidden_size, device=gpu)
        self.out = nn.Linear(hidden_size, output_size, device=gpu)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        if hasattr(self, "fc3"):
            x = F.relu(self.fc3(x))
            x = F.relu(self.fc4(x))

        # Output move_x, move_y directly as continuous values
        x = self.out(x)
        return x
    
class MultiMoveNetwork(nn.Module):
    def __init__(self, input_size=4, hidden_size=64, num_moves=5):
        super(MultiMoveNetwork, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        
        # Each move has 2 outputs (move_x, move_y)
        output_size = 2 * num_moves
        self.out = nn.Linear(hidden_size, output_size)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.out(x)  # returns a vector of length 10 if num_moves=5
    

class Conv1DNetwork(nn.Module):
    def __init__(self, input_channels=4, output_size=2):
        super(Conv1DNetwork, self).__init__()
        
        # First conv layer: from 4 channels to 16 filters
        self.conv1 = nn.Conv1d(in_channels=input_channels, out_channels=16, kernel_size=3, stride=1, padding=1)
        
        # Second conv layer: from 16 filters to 32 filters
        self.conv2 = nn.Conv1d(in_channels=16, out_channels=32, kernel_size=3, stride=1, padding=1)
        
        # Pooling layer halves the sequence length
        # If input length is 100, after pooling it becomes 50.
        self.pool = nn.MaxPool1d(kernel_size=2, stride=2)
        
        # After conv/pool:
        # - Number of channels = 32
        # - Sequence length = 100/2 = 50
        # Flattened size = 32 * 50 = 1600
        self.fc = nn.Linear(32 * 50, output_size)
        
    def forward(self, x):
        # x: (batch_size, 4, sequence_length)
        x = F.relu(self.conv1(x))    # (batch_size, 16, sequence_length)
        x = F.relu(self.conv2(x))    # (batch_size, 32, sequence_length)
        x = self.pool(x)             # (batch_size, 32, sequence_length/2) 
                                     # If input length=100, now (batch_size, 32, 50)
        
        x = x.view(x.size(0), -1)    # Flatten: (batch_size, 1600)
        x = self.fc(x)               # (batch_size, 2)
        return x
