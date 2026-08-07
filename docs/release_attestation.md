# 正式审核发布凭证

企业微信正式审核通知默认需要独立发布签发器的凭证。审核框架只持有签发公钥，不能在审核目录中生成、替换或重新签署凭证。

签发器应在审核目录已生成 HTML、所有审核闭环完成后，创建 `release_attestation.json` 并对该文件原始字节生成 `release_attestation.sig`。私钥必须保存在审核工作区和通知配置之外的受控系统中。

凭证结构为：

```json
{
  "schema_version": "1.0",
  "project_id": "26YLM139F",
  "issued_at": "2026-07-30T10:00:00+00:00",
  "expires_at": "2026-07-30T10:15:00+00:00",
  "nonce": "one-time-release-id",
  "artifacts": {
    "final_decision": {"path": "final_decision.json", "sha256": "..."},
    "arbitration_resolution": {"path": "agent_results/arbitration/arbitration_resolution.json", "sha256": "..."},
    "visual_audit_result": {"path": "visual_audit_result.json", "sha256": "..."},
    "final_review_report": {"path": "final_review_report.md", "sha256": "..."},
    "html_report": {"path": "<project>_audit_report.html", "sha256": "..."}
  }
}
```

配置中的 `release_attestation_gate.public_key_path` 必须指向工作区外的绝对公钥路径。未配置公钥、缺少签名、签名无效、超过有效期、项目号不匹配或任一绑定产物变化，都会在任何网络请求前拒绝通知；拒绝后也不会降级到备用通知渠道。签名验证通过后，框架会在网络请求前原子写入 `.release_attestation_consumptions/<凭证哈希>.json`；同一凭证不能再次发送，网络状态不明时也必须重新签发。
