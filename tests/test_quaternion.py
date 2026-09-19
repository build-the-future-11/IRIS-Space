from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from siderea.ml.quaternion import (  # noqa: E402
    QuaternionCausalAttention,
    QuaternionLinear,
    hamilton_product,
    quaternion_conjugate,
    quaternion_inverse,
    quaternion_norm,
    quaternion_real_matrix,
)


def test_quaternion_multiplication_table_and_noncommutativity() -> None:
    one = torch.tensor([1.0, 0.0, 0.0, 0.0])
    i = torch.tensor([0.0, 1.0, 0.0, 0.0])
    j = torch.tensor([0.0, 0.0, 1.0, 0.0])
    k = torch.tensor([0.0, 0.0, 0.0, 1.0])
    assert torch.equal(hamilton_product(one, i), i)
    assert torch.equal(hamilton_product(i, i), -one)
    assert torch.equal(hamilton_product(i, j), k)
    assert torch.equal(hamilton_product(j, i), -k)


def test_conjugate_inverse_and_norm_multiplicativity() -> None:
    generator = torch.Generator().manual_seed(7)
    left = torch.randn((128, 4), generator=generator, dtype=torch.float64)
    right = torch.randn((128, 4), generator=generator, dtype=torch.float64)
    product = hamilton_product(left, right)
    assert torch.allclose(
        quaternion_norm(product), quaternion_norm(left) * quaternion_norm(right), atol=1e-12
    )
    identity = hamilton_product(left, quaternion_inverse(left))
    expected = torch.zeros_like(identity)
    expected[:, 0] = 1.0
    assert torch.allclose(identity, expected, atol=1e-12)
    squared = hamilton_product(left, quaternion_conjugate(left))
    assert torch.allclose(squared[:, 1:], torch.zeros_like(squared[:, 1:]), atol=1e-12)


def test_pure_quaternion_product_is_dot_and_cross() -> None:
    u = torch.tensor([0.0, 1.0, 2.0, 3.0])
    v = torch.tensor([0.0, -2.0, 4.0, 1.0])
    product = hamilton_product(u, v)
    assert torch.allclose(product[0], -torch.dot(u[1:], v[1:]))
    assert torch.allclose(product[1:], torch.linalg.cross(u[1:], v[1:]))


def test_real_matrix_matches_hamilton_product() -> None:
    generator = torch.Generator().manual_seed(11)
    weight = torch.randn((5, 4), generator=generator, dtype=torch.float64)
    value = torch.randn((5, 4), generator=generator, dtype=torch.float64)
    matrix = quaternion_real_matrix(weight)
    expected = torch.einsum("bij,bj->bi", matrix, value)
    assert torch.allclose(hamilton_product(weight, value), expected, atol=1e-12)


def test_quaternion_linear_matches_explicit_sum() -> None:
    layer = QuaternionLinear(3, 2).double()
    value = torch.randn((4, 3, 4), dtype=torch.float64)
    actual = layer(value)
    expected = torch.stack(
        [
            torch.stack(
                [
                    sum(
                        (hamilton_product(layer.weight[o, i], value[b, i]) for i in range(3)),
                        start=torch.zeros(4, dtype=torch.float64),
                    )
                    + layer.bias[o]
                    for o in range(2)
                ]
            )
            for b in range(4)
        ]
    )
    assert torch.allclose(actual, expected, atol=1e-12)


def test_quaternion_linear_gradcheck() -> None:
    layer = QuaternionLinear(2, 2).double()
    value = torch.randn((2, 2, 4), dtype=torch.float64, requires_grad=True)
    assert torch.autograd.gradcheck(layer, (value,), eps=1e-6, atol=1e-4)


def test_causal_attention_does_not_read_future_or_padding() -> None:
    torch.manual_seed(19)
    layer = QuaternionCausalAttention(4, 2, dropout=0.0).eval()
    value = torch.randn((1, 4, 4, 4))
    mask = torch.tensor([[True, True, True, False]])
    original = layer(value, mask)
    changed = value.clone()
    changed[:, 2:] = 10000.0
    modified = layer(changed, mask)
    assert torch.allclose(original[:, :2], modified[:, :2], atol=1e-5)
    assert torch.equal(original[:, 3], torch.zeros_like(original[:, 3]))
