# SecGuard abstracts

## English abstract

End-to-end network slices share radio, transport, and compute infrastructure,
creating an economic tension between multiplexing and cross-slice isolation.
5Guard models three isolation levels but treats the requested level as fixed.
This paper presents SecGuard, a proof-of-concept extension that maps 5G packet
and GTP telemetry to slice risk, applies an SLA-safe isolation or quarantine
action, and passes the adapted request to the unmodified 5Guard allocator. A
Random Forest classifier supplies packet risk, while two Random Forest
regressors approximate profit and isolation exposure across 165 threshold
policies. On 30 held-out trace-derived scenarios, learned SecGuard increased
mean profit by 164.92% over a fixed-threshold controller (two-sided paired
Wilcoxon p=0.0028, Cohen's dz=0.69). Against static 5Guard, it retained 90.44%
of mean profit while reducing a modeled isolation-exposure proxy by 67.12%
(p=2.56e-6, dz=-3.43). Its held-out profit was 2.41% below a training-set
exhaustive oracle, but an equal-budget random search found that same oracle;
the experiment therefore does not establish surrogate superiority over random
search. A quarantine ablation further shows that the current proxy cannot
distinguish quarantine from L2 isolation. The results support a reproducible
risk-to-allocation integration, while cross-dataset detection and measured
attack propagation remain necessary for broader claims.

**Keywords:** security orchestration, intrusion detection, constrained policy
selection, service-level agreement, Pareto analysis, resource allocation

## Traditional Chinese abstract

端到端網路切片藉由共享無線、傳輸與運算資源提高利用率，卻也增加跨切片風險。5Guard可依三種隔離等級配置資源，但不會根據執行期流量調整申請中的隔離需求。本研究提出SecGuard概念驗證系統，利用隨機森林從5G封包與GTP特徵估計風險，再以不低於服務等級協議的安全規則決定保留、升級或隔離切片；另一組迴歸模型則在安全限制下選擇門檻。於三十組未參與門檻選擇的情境中，SecGuard相較固定門檻策略使平均利潤提高164.92%（配對Wilcoxon檢定p=0.0028，dz=0.69）；相較靜態5Guard則保留90.44%利潤，並使模型化暴露指標降低67.12%（p=2.56×10^-6，dz=-3.43）。然而，同等評估預算的隨機搜尋亦找到訓練集最佳策略，且現有暴露指標無法區分L2隔離與完全移除。結果支持風險驅動隔離與5Guard配置器整合的可行性，但尚不足以證明機器學習搜尋優於隨機搜尋，也不能代表實際攻擊阻斷效果。

**關鍵詞：** 安全編排、入侵偵測、受限策略選擇、服務等級協議、帕累托分析、資源配置

## Quality record

- Both abstracts cover background, purpose, method, findings, and implication.
- English length: within the ARS 150–300 word target.
- Traditional Chinese length: designed for the ARS 300–500 character target.
- Six keywords are supplied in each language.
- The Chinese abstract was independently composed and preserves the English
  abstract's numerical claims and qualifications.
