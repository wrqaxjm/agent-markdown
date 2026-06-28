---
$schema: amd/v1
$id: adam-paper
$type: source-page
$fields:
  arxiv_id: '1412.6980'
  year: 2014
  authors:
  - Kingma, D.P.
  - Ba, J.
  tags:
  - optimizer
  - adaptive-gradient
  - deep-learning
$updated: '2026-06-28T23:00:00Z'
$updated_by: agent:mavis:414131408429400
---

# Adam: A Method for Stochastic Optimization

## §1 Summary {#s1 .abstract required}

Kingma & Ba (2014) propose Adam, an algorithm for first-order gradient-based optimization of stochastic objective functions, based on adaptive estimates of lower-order moments. The method is computationally efficient, has little memory requirement, and is well-suited for problems with large data and/or parameters. Adam is invariant to diagonal rescaling of gradients, and is appropriate for non-stationary objectives and problems with very noisy and/or sparse gradients.

## §2 Method {#s2 .method required}

### §2.1 Algorithm {#s2.1 .algorithm}

The algorithm updates exponential moving averages of the gradient ($m_t$) and the squared gradient ($v_t$) where the hyper-parameters $\beta_1, \beta_2 \in [0, 1)$ control the exponential decay rates.

$$m_t = \beta_1 m_{t-1} + (1 - \beta_1) g_t$$
$$v_t = \beta_2 v_{t-1} + (1 - \beta_2) g_t^2$$
$$\hat{m}_t = m_t / (1 - \beta_1^t)$$
$$\hat{v}_t = v_t / (1 - \beta_2^t)$$
$$\theta_t = \theta_{t-1} - \alpha \cdot \hat{m}_t / (\sqrt{\hat{v}_t} + \epsilon)$$

### §2.2 Bias Correction {#s2.2}

The exponential moving averages are initialized to zero, so the authors include bias correction terms to counteract the initialization bias.

## §3 Figures {#s3 .figures required}

@figure {
  src: "figures/adam-fig1.png"
  alt: "Loss curves comparison on MNIST autoencoder"
  caption: "Figure 1: Logistic regression and MNIST autoencoder training loss."
  width: 0.8
}

@figure {
  src: "figures/adam-fig2.png"
  alt: "Convergence on different optimizers"
  caption: "Figure 2: Comparison with other adaptive learning methods."
  width: 0.8
}

## §4 References {#s4 .backlinks required}

@backlink {
  from: "[[Adam]]"
  kind: defines
  confidence: 1.0
}

@backlink {
  from: "[[Optimizer]]"
  kind: instance-of
  confidence: 0.95
}

@backlink {
  from: "[[AdamW]]"
  kind: extends
  confidence: 0.85
}
