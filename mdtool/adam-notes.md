---
title: "Adam: A Method for Stochastic Optimization"
type: source
arxiv_id: "1412.6980"
year: 2014
authors: ["Kingma, D.P.", "Ba, J."]
venue: ICLR 2015
categories: [cs.LG, stat.ML]
subcategory: optimizer
tags: [adaptive-gradient, deep-learning, 优化器]
last_updated: 2026-06-28
pdf_path: F:\arxiv-lunwen\cs.LG\optimizer\Adam_A_Method_for_Stochastic_Optimization__1412.6980.pdf
mineru_path: F:\arxiv-lunwen\cs.LG\optimizer\Adam_A_Method_for_Stochastic_Optimization__1412.6980_mineru.md
---

# Adam 优化器论文笔记

## 📝 一句话总结

Adam 将 Momentum 和 RMSProp 结合起来，通过 bias correction 解决冷启动问题，是目前最常用的深度学习优化器之一。

## 🔬 解决什么问题

训练深层神经网络时，SGD 收敛慢、需要精细调参。Adam 提供了一种**自适应学习率**方法：
- 对每个参数维护一阶矩（mean）和二阶矩（uncentered variance）的指数移动平均
- 通过 bias correction 修正初始时刻的偏差
- 实际使用中几乎不需要调参（默认 lr=0.001, β₁=0.9, β₂=0.999）

## ⚙️ 核心方法

### 算法伪代码

```
m₀ = 0, v₀ = 0
for t = 1 to T:
    gₜ = ∇f(θₜ₋₁)
    mₜ = β₁·mₜ₋₁ + (1-β₁)·gₜ      # 一阶矩估计
    vₜ = β₂·vₜ₋₁ + (1-β₂)·gₜ²     # 二阶矩估计
    m̂ₜ = mₜ / (1-β₁ᵗ)              # bias correction
    v̂ₜ = vₜ / (1-β₂ᵗ)
    θₜ = θₜ₋₁ - α·m̂ₜ/(√v̂ₜ + ε)
```

关键洞察：指数移动平均初始化为 0 会导致早期步骤偏向 0，**bias correction** 通过除以 (1-βᵗ) 来修正。

### 收敛性分析

理论保证：对于凸函数，Adam 的 regret bound 是 O(√T)；对于非凸随机优化，收敛到 stationary point。详见 Theorem 4.1。

## 📊 实验与数据

### 对比实验

Adam 在以下任务上对比了 SGD、AdaGrad、RMSProp：

1. **MNIST 图像分类**：逻辑回归 + 多层神经网络
   - Adam 收敛最快，最终准确率与 SGD with momentum 持平
   
2. **IMDB 情感分析**：LSTM 模型
   - Adam 在 10 epochs 内达到 88.7% accuracy
   
3. **CIFAR-10**：卷积神经网络
   - Adam 不需要调整 learning rate schedule

### 关键图表

![Figure 1: MNIST 上不同优化器的训练 loss 对比](F:\arxiv-lunwen\cs.LG\optimizer\Adam_1412.6980_图片\fig1_loss_comparison.png)

![Figure 2: 不同 β₁ β₂ 组合对收敛速度的影响](F:\arxiv-lunwen\cs.LG\optimizer\Adam_1412.6980_图片\fig2_beta_ablation.png)

![Figure 3: Adam vs RMSProp vs AdaGrad 在 CIFAR-10 上的结果](F:\arxiv-lunwen\cs.LG\optimizer\Adam_1412.6980_图片\fig3_cifar10.png)

## 🎯 关键结论

1. Adam 结合了 AdaGrad（处理稀疏梯度）和 RMSProp（处理非平稳目标）的优点
2. Bias correction 是关键创新——没有它，初始步骤的步长会过大
3. 超参数鲁棒性强：β₁, β₂, ε 的默认值在大多数任务上表现良好
4. 计算高效、内存需求低、适合大规模数据和参数

## ⚠️ 局限性

- 在某些任务上泛化性能不如 SGD with momentum（如 ImageNet 分类）
- 理论收敛性假设较强（凸函数、有界梯度），实际可能不满足
- 后续工作 AdamW 指出 L2 正则化和 weight decay 在 Adam 中不等价

## 🔗 与其他工作的关系

See [[AdamW]] for decoupled weight decay fix.
See [[AdaGrad]] for the precursor that inspired per-parameter learning rates.
See [[RMSProp]] for the moving average of squared gradients idea.
See [[AmsGrad]] for a convergence fix attempt.
See [[NAdam]] for Nesterov momentum + Adam.

## 💬 我的笔记

这篇论文写得非常清晰。Algorithm 1 只有 7 行伪代码，但每行都有充足的理由。bias correction 的想法很巧妙——用指数移动平均的期望公式推导出修正因子。

不过实际使用中，AdamW 已经基本取代了原始 Adam。weight decay 和 L2 regularization 在自适应优化器中的不等价性值得单独写一篇笔记。

中文社区习惯把 "自适应矩估计" 翻译为 Adaptive Moment Estimation，但 Adam 这个名字其实来自 "ADAptive Moment estimation" —— 把首字母拼起来就是 Adam。
