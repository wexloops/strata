import itertools

import pytest
import torch

from allin1.models import natten_torch

reference = pytest.importorskip('natten.functional')
if not hasattr(reference, 'natten1dqkrpb'):
  pytest.skip('this NATTEN release no longer has the functions to compare against', allow_module_level=True)


@pytest.mark.parametrize('length,kernel_size,dilation', [
  case for case in itertools.product([7, 16, 33, 50], [3, 5, 7], [1, 2, 3, 4]) if case[0] >= case[1] * case[2]
])
def test_1d_matches_natten(length, kernel_size, dilation):
  torch.manual_seed(0)
  query, key, value = (torch.randn(2, 3, length, 8) for _ in range(3))
  rpb = torch.randn(3, 2 * kernel_size - 1)
  expected = reference.natten1dqkrpb(query, key, rpb, kernel_size, dilation)
  scores = natten_torch.natten1dqkrpb(query, key, rpb, kernel_size, dilation)
  torch.testing.assert_close(scores, expected, atol=1e-4, rtol=1e-4)
  torch.testing.assert_close(
    natten_torch.natten1dav(scores.softmax(-1), value, kernel_size, dilation),
    reference.natten1dav(expected.softmax(-1), value, kernel_size, dilation),
    atol=1e-4, rtol=1e-4,
  )


@pytest.mark.parametrize('size,kernel_size,dilation', [
  case for case in itertools.product([(9, 12), (20, 15), (31, 17)], [3, 5], [1, 2, 3])
  if min(case[0]) >= case[1] * case[2]
])
def test_2d_matches_natten(size, kernel_size, dilation):
  torch.manual_seed(0)
  height, width = size
  query, key, value = (torch.randn(2, 3, height, width, 8) for _ in range(3))
  rpb = torch.randn(3, 2 * kernel_size - 1, 2 * kernel_size - 1)
  expected = reference.natten2dqkrpb(query, key, rpb, kernel_size, dilation)
  scores = natten_torch.natten2dqkrpb(query, key, rpb, kernel_size, dilation)
  torch.testing.assert_close(scores, expected, atol=1e-4, rtol=1e-4)
  torch.testing.assert_close(
    natten_torch.natten2dav(scores.softmax(-1), value, kernel_size, dilation),
    reference.natten2dav(expected.softmax(-1), value, kernel_size, dilation),
    atol=1e-4, rtol=1e-4,
  )


def test_gradients_flow():
  query, key = (torch.randn(1, 2, 12, 4, requires_grad=True) for _ in range(2))
  rpb = torch.randn(2, 5, requires_grad=True)
  natten_torch.natten1dqkrpb(query, key, rpb, 3, 2).sum().backward()
  assert query.grad is not None and key.grad is not None and rpb.grad is not None
