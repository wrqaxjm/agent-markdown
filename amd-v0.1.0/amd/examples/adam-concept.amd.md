---
$schema: amd/v1
$id: adam-concept
$type: concept-page
$fields:
  tags: [optimizer, algorithm, deep-learning]
  related: ["adamw", "rmsprop", "sgd"]
$updated: 2026-06-28T23:10:00Z
---

# Adam (concept)

## §1 Definition {#s1 .definition required}

**Adam** (Adaptive Moment Estimation) is an optimization algorithm for stochastic gradient descent, introduced by Kingma and Ba in 2014. It computes adaptive learning rates for each parameter from estimates of the first and second moments of the gradients.

## §2 Mechanism {#s2 .mechanism}

Adam maintains two exponentially-decaying running averages per parameter:
- $m_t$ — the first moment (mean) of gradients
- $v_t$ — the second moment (uncentered variance) of gradients

The parameter update combines bias-corrected versions of both.

## §3 Connections {#s3 .connections}

- **SGD with momentum**: Adam = RMSProp + momentum.
- **RMSProp**: Adam's per-parameter scaling without the momentum term.
- **AdamW**: Adam with decoupled weight decay (Loshchilov & Hutter, 2019).

@backlink {
  from: "[[AdamW]]"
  kind: parent-of
}

@backlink {
  from: "[[RMSProp]]"
  kind: extends
}

## §4 Tradeoffs {#s4 .tradeoffs}

**Pros**:
- Works well out-of-the-box with default hyperparameters
- Handles sparse gradients effectively
- Computationally efficient

**Cons**:
- Can converge to sharp minima (worse generalization)
- May not match SGD with momentum on some tasks (e.g., image classification with strong augmentation)
- Requires bias correction