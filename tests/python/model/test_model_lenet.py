# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

# pylint: disable=protected-access
import pytest
import torch
import torch.nn as nn
import torch.nn.functional as F

import mnm
from mnm.model import Conv2d, Linear
from mnm.testing import check, one_hot_torch, randn_torch, t2m_param, run_vm_model


class TorchLeNet(nn.Module):  # pylint: disable=abstract-method
    def __init__(self, input_shape=28, num_classes=10):
        super(TorchLeNet, self).__init__()
        self.conv1 = nn.Conv2d(in_channels=3, out_channels=6, kernel_size=5, padding=2, bias=False)
        self.conv2 = nn.Conv2d(in_channels=6, out_channels=16, kernel_size=5, bias=False)
        self.linear1 = nn.Linear(((input_shape // 2 - 4) // 2) ** 2 * 16, 120)
        self.linear2 = nn.Linear(120, 84)
        self.linear3 = nn.Linear(84, num_classes)

    def forward(self, x, y_true):  # pylint: disable=arguments-differ
        y_pred = self.forward_infer(x)
        y_pred = F.log_softmax(y_pred, dim=-1)
        loss = F.nll_loss(y_pred, y_true)
        return loss

    def forward_infer(self, x):
        out = self.conv1(x)
        out = torch.sigmoid(out)  # pylint: disable=no-member
        out = F.avg_pool2d(out, (2, 2), (2, 2))
        out = self.conv2(out)
        out = torch.sigmoid(out)  # pylint: disable=no-member
        out = F.avg_pool2d(out, (2, 2), (2, 2))
        out = torch.flatten(out, 1)  # pylint: disable=no-member
        out = self.linear1(out)
        out = self.linear2(out)
        out = self.linear3(out)
        return out


class MNMLeNet(mnm.Model):
    # pylint: disable=attribute-defined-outside-init
    def build(self, input_shape=28, num_classes=10):
        self.conv1 = Conv2d(in_channels=3, out_channels=6, kernel_size=5, padding=2, bias=False)
        self.conv2 = Conv2d(in_channels=6, out_channels=16, kernel_size=5, bias=False)
        self.linear1 = Linear(((input_shape // 2 - 4) // 2) ** 2 * 16, 120)
        self.linear2 = Linear(120, 84)
        self.linear3 = Linear(84, num_classes)

    # pylint: enable=attribute-defined-outside-init

    @mnm.model.trace
    def forward(self, x, y_true):
        y_pred = self.forward_infer(x)
        y_pred = mnm.log_softmax(y_pred)
        loss = mnm.nll_loss(y_true=y_true, y_pred=y_pred)
        return loss

    @mnm.model.trace
    def forward_infer(self, x):
        out = self.conv1(x)
        out = mnm.sigmoid(out)
        out = mnm.avg_pool2d(out, (2, 2), (2, 2))
        out = self.conv2(out)
        out = mnm.sigmoid(out)
        out = mnm.avg_pool2d(out, (2, 2), (2, 2))
        out = mnm.batch_flatten(out)
        out = self.linear1(out)
        out = self.linear2(out)
        out = self.linear3(out)
        return out


@pytest.mark.skipif(not mnm.build.with_cuda(), reason="CUDA is not enabled")
@pytest.mark.parametrize(
    "config",
    [
        (224, 1000),
        (32, 100),
        (32, 10),
        (28, 10),
    ],
)
def test_lenet(config):
    t_model = TorchLeNet(*config)
    t_model.to(device="cuda")
    m_model = MNMLeNet(*config)
    m_model.to(device="cuda")
    m_model.conv1.w = t2m_param(t_model.conv1.weight)
    m_model.conv2.w = t2m_param(t_model.conv2.weight)
    m_model.linear1.w = t2m_param(t_model.linear1.weight)
    m_model.linear1.b = t2m_param(t_model.linear1.bias)
    m_model.linear2.w = t2m_param(t_model.linear2.weight)
    m_model.linear2.b = t2m_param(t_model.linear2.bias)
    m_model.linear3.w = t2m_param(t_model.linear3.weight)
    m_model.linear3.b = t2m_param(t_model.linear3.bias)
    m_x, t_x = randn_torch([1, 3, config[0], config[0]], requires_grad=True, device="cuda")
    m_y, t_y = one_hot_torch(batch_size=1, num_classes=config[1], device="cuda")

    print("### Switch to training mode")
    m_model.train_mode()
    t_model.train()
    m_loss = m_model(m_x, m_y)
    t_loss = t_model(t_x, t_y)
    m_loss.backward()
    t_loss.backward()
    check(m_loss, t_loss)
    check(m_model.conv1.w.grad, t_model.conv1.weight.grad, rtol=1e-4, atol=1e-4)
    check(m_model.conv2.w.grad, t_model.conv2.weight.grad, rtol=1e-4, atol=1e-4)
    check(m_model.linear1.w.grad, t_model.linear1.weight.grad, rtol=1e-4, atol=1e-4)
    check(m_model.linear1.b.grad, t_model.linear1.bias.grad, rtol=1e-4, atol=1e-4)
    check(m_model.linear2.w.grad, t_model.linear2.weight.grad, rtol=1e-4, atol=1e-4)
    check(m_model.linear2.b.grad, t_model.linear2.bias.grad, rtol=1e-4, atol=1e-4)
    check(m_model.linear3.w.grad, t_model.linear3.weight.grad, rtol=1e-4, atol=1e-4)
    check(m_model.linear3.b.grad, t_model.linear3.bias.grad, rtol=1e-4, atol=1e-4)

    print("### Switch to infer mode")
    m_model.infer_mode()
    t_model.eval()
    m_model(m_x)
    t_model(t_x, t_y)


@pytest.mark.skipif(not mnm.build.with_cuda(), reason="CUDA is not enabled")
@pytest.mark.parametrize(
    "config",
    [
        (32, 100),
        (28, 10),
    ],
)
def test_lenet_amp(config):
    t_model = TorchLeNet(*config)
    t_model.to(device="cuda")
    m_model = MNMLeNet(*config)
    m_model.to(device="cuda")
    m_model.conv1.w = t2m_param(t_model.conv1.weight)
    m_model.conv2.w = t2m_param(t_model.conv2.weight)
    m_model.linear1.w = t2m_param(t_model.linear1.weight)
    m_model.linear1.b = t2m_param(t_model.linear1.bias)
    m_model.linear2.w = t2m_param(t_model.linear2.weight)
    m_model.linear2.b = t2m_param(t_model.linear2.bias)
    m_model.linear3.w = t2m_param(t_model.linear3.weight)
    m_model.linear3.b = t2m_param(t_model.linear3.bias)
    m_x, t_x = randn_torch([1, 3, config[0], config[0]], requires_grad=False, device="cuda")

    m_model.infer_mode()
    t_model.eval()
    with torch.cuda.amp.autocast():
        t_y = t_model.forward_infer(t_x)
    m_y = run_vm_model(m_model, "cuda", [m_x], pass_seq=mnm._ffi.pass_.AutoCast())
    check(m_y, t_y, rtol=1e-3, atol=1e-3)


if __name__ == "__main__":
    pytest.main([__file__])
