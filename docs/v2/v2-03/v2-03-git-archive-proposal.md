# V2 03 建议归档范围（尚未授权执行）

后续授权：用户已明确指示“提交并push git”，本范围现获准执行；下文保留技术交付时的归档建议，实际提交及远端核验以后续归档回执为准。

本轮仅技术QA与交付；不执行Git暂存、提交、推送或合并。基线为`v2`分支、`1f3d73643af84fdc55f7f314d6c0db6f0c34560a`，最终实际清单见[evidence/v2-03-git-workspace.json](evidence/v2-03-git-workspace.json)。

后续人工验收并另行授权Git归档时，可纳入：

- V2 03工具metadata、Registry/discovery/selector，专业图选择/绑定接线、State白名单，Runtime/Gateway/Scope/compactor及Task Saver消费记录。
- `.env.example`公开参数示例，`app/core/config.py`和`app/main.py`必要装配。
- 渐进式工具受控测试、显式手动真实入口，以及Graph协议、退款Checkpoint测试替身的必要更新。
- 根README、docs/STATE及V2导航，V2 03协调/裁决、修复记录、独立QA、原始失败与通过证据、最终交付报告。

继续排除接管时已有的4项无关untracked文件：`app/agents/prompts/general.py`、`scripts/rehearse_v2_01_pg1712_restore.py`、`scripts/upgrade_v2_01_pg1712.py`、`scripts/verify_v2_01_pg1712_compatibility.py`，不覆盖或删除。其hash已单独保护。

不得归档真实`.env`、`.git`下凭据/私有helper、环境临时目录或数据库卷。V1/V2 01/V2 02历史交付及冻结设计保持，不把这些既存内容重复归入本阶段修改。无需为3条既有Ruff E501引入无关格式改动。
