"""시드 고정. 실험 스크립트 맨 앞에서 set_seed(cfg["seed"])를 부른다.

GPU에서는 시드를 고정해도 일부 연산이 비결정적이라 결과가 조금 다를 수 있다.
완전 결정성이 필요하면 deterministic=True (느려질 수 있음, 지원하지 않는 연산은 오류).
"""
import os
import random

import numpy as np


def set_seed(seed: int, deterministic: bool = False) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)  # 이미 실행 중인 프로세스의 hash에는 영향 없음(하위 프로세스용)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)  # CPU와 모든 CUDA 장치
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False


def seed_worker(worker_id: int) -> None:
    """DataLoader(worker_init_fn=seed_worker, generator=g)용. g = torch.Generator().manual_seed(seed)
    macOS·Windows에서 num_workers>0이면 실행 코드를 `if __name__ == "__main__":` 안에 둬야 한다(spawn 방식)."""
    import torch
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


if __name__ == "__main__":
    set_seed(0)
    a = np.random.rand(3)
    set_seed(0)
    assert np.allclose(a, np.random.rand(3))
    print("seed ok", a)
