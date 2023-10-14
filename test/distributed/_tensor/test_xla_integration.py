# Copyright (c) Meta Platforms, Inc. and affiliates
# Owner(s): ["oncall: distributed"]

import os
import unittest
from functools import wraps
from typing import Any, Callable, Dict, Tuple

import torch
from torch.distributed._tensor import DeviceMesh, distribute_tensor, Shard
from torch.testing._internal.common_utils import run_tests, TestCase


# wrapper to check xla test requirements
def with_xla(func: Callable) -> Callable:
    assert func is not None

    @wraps(func)  # pyre-ignore[6]
    def wrapper(
        self, *args: Tuple[object], **kwargs: Dict[str, Any]  # type: ignore[misc]
    ) -> None:
        # TODO(yeounoh) replace this with xr.use_spmd() when we deprecate the flag.
        os.environ["XLA_USE_SPMD"] = "1"
        try:
            import torch_xla  # type:ignore[import]  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("torch_xla is not installed.") from exc
        self.device_type = "xla"
        func(self, *args, **kwargs)  # type: ignore[misc]
        os.environ["XLA_USE_SPMD"] = "0"

    return wrapper


class DTensorXLAIntegrationTest(TestCase):
    @property
    def device_count(self) -> int:
        return 4

    @with_xla
    def test_xla_distribute_tensor(self):
        device_mesh = DeviceMesh("xla", list(range(self.device_count)))
        shard_spec = [Shard(0)]

        for requires_grad in [True, False]:
            tensor_to_shard = torch.randn(
                3 * self.device_count, 3, requires_grad=requires_grad
            )
            dist_tensor = distribute_tensor(tensor_to_shard, device_mesh, shard_spec)
            # TODO(yeounoh) switch to DTensor API when XLAShardedTensor inherits DTensor
            assert type(dist_tensor).__name__ == "XLAShardedTensor"
            global_tensor = dist_tensor.global_tensor  # type:ignore[attr-defined]
            self.assertEqual(
                global_tensor.size(), torch.Size([3 * self.device_count, 3])
            )
            local_tensor = dist_tensor.local_shards[0].data
            self.assertEqual(local_tensor.size(), torch.Size([3, 3]))
            if requires_grad:
                self.assertTrue(dist_tensor.global_tensor.requires_grad)
                self.assertTrue(dist_tensor.is_leaf)


if __name__ == "__main__":
    run_tests()
