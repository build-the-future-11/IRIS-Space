import json, math
import torch
from torch import nn
from siderea.ml.space_jepa_v2_train import train_space_jepa_v2, SpaceJEPA2TrainingConfig

class Fixture(nn.Module):
    def __init__(self, scale):
        super().__init__()
        self.context_encoder = nn.Linear(1, 4, bias=False)
        nn.init.zeros_(self.context_encoder.weight)
        self.predictor = nn.Identity()
        self.ema_calls = 0
        self.scale = scale
    def forward(self, context, mask):
        return {'base_forecast': self.context_encoder.weight.reshape(1,1,1,4).expand(len(context),1,1,4) * self.scale}
    def encode_targets(self, targets, mask):
        return torch.ones((len(targets),1,1,4))
    def update_target(self, momentum):
        self.ema_calls += 1

batch = {'context_tokens': torch.zeros((2,1,1)), 'context_mask': torch.ones((2,1),dtype=torch.bool), 'target_tokens': torch.ones((2,1,1,1)), 'target_mask': torch.ones((2,1,1),dtype=torch.bool)}
for scale in [1.0, 1e20, 1e30]:
    model = Fixture(scale)
    raw_gradients=[]
    model.context_encoder.weight.register_hook(lambda grad: raw_gradients.append(grad.detach().clone()))
    result = train_space_jepa_v2(model, [batch], [batch], SpaceJEPA2TrainingConfig(epochs=1,seed=7))
    print(json.dumps({'scale':scale, 'train_loss': str(result['history'][0]['train_loss']), 'validation_loss':str(result['final_validation_loss']), 'gradient_finite':bool(torch.isfinite(raw_gradients[0]).all()), 'gradient_max':str(raw_gradients[0].abs().max().item()), 'weights': [str(x) for x in model.context_encoder.weight.flatten().tolist()], 'ema_updates': model.ema_calls, 'global_steps':result['global_steps']}))
