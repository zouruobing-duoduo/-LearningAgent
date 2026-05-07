"""读取飞书知识库内容"""
import json
import requests

APP_ID = "cli_a954b51ad2b8dcd3"
APP_SECRET = "cNIwgCy4ZQFAnqP2mD3CjfsjNyq8lpsX"
SPACE_ID = "7628530521119149241"

# 获取 token
token_resp = requests.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": APP_ID, "app_secret": APP_SECRET},
)
token = token_resp.json()["tenant_access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 列出知识库节点
print("=== 知识库节点列表 ===")
nodes_resp = requests.get(
    f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{SPACE_ID}/nodes?page_size=50",
    headers=headers,
)
nodes_data = nodes_resp.json()
print(json.dumps(nodes_data, ensure_ascii=False, indent=2))

# 如果有节点，读取每个节点的内容
items = nodes_data.get("data", {}).get("items", [])
for item in items:
    node_token = item.get("node_token", "")
    obj_token = item.get("obj_token", "")
    title = item.get("title", "")
    obj_type = item.get("obj_type", "")
    print(f"\n=== 节点: {title} (type={obj_type}, obj_token={obj_token}) ===")
    
    if obj_type == "doc" or obj_type == "docx":
        # 读取文档内容
        doc_resp = requests.get(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{obj_token}/raw_content",
            headers=headers,
        )
        print(json.dumps(doc_resp.json(), ensure_ascii=False, indent=2))
