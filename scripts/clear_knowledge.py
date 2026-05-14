#!/usr/bin/env python3
"""
清空知识库数据脚本

用于删除所有测试数据，准备导入真实文章
"""
import requests
import sys

API_BASE = "http://localhost:8001"

def get_token():
    """获取匿名 Token"""
    response = requests.post(f"{API_BASE}/api/auth/anonymous")
    return response.json()["token"]

def list_articles(token):
    """获取文章列表"""
    response = requests.get(
        f"{API_BASE}/api/knowledge/articles",
        headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()

def delete_article(token, article_id):
    """删除文章"""
    response = requests.delete(
        f"{API_BASE}/api/knowledge/articles/{article_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    return response.status_code == 200

def main():
    print("🗑️  清空知识库数据")
    print("=" * 50)
    
    # 获取 Token
    token = get_token()
    
    # 获取文章列表
    articles = list_articles(token)
    
    if not articles:
        print("✅ 知识库已经是空的")
        return
    
    print(f"📋 找到 {len(articles)} 篇文章：")
    for article in articles:
        print(f"   - {article['title']}")
    
    # 确认删除
    print("\n⚠️  即将删除所有文章及其分块数据")
    confirm = input("确认删除？(y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ 取消删除")
        return
    
    # 删除文章
    print("\n🔄 正在删除...")
    success_count = 0
    for article in articles:
        if delete_article(token, article['id']):
            print(f"   ✅ 删除: {article['title']}")
            success_count += 1
        else:
            print(f"   ❌ 失败: {article['title']}")
    
    print(f"\n✅ 删除完成: {success_count}/{len(articles)} 篇文章")

if __name__ == "__main__":
    main()
