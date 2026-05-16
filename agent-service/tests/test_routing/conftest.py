"""
test_routing 专用 conftest

在导入 Orchestrator 前 mock 掉 app.models.memory 模块，
避免 history_manager 导入 ConversationMemory 时触发
SQLAlchemy 'metadata' 保留属性错误。
"""
import sys
import types
from unittest.mock import MagicMock

# 创建 mock 模块，避免 app.models.memory 被实际加载
# 生产代码中 ConversationMemory 使用了 'metadata' 作为列名，
# 与 SQLAlchemy Declarative API 的保留属性冲突
_orig_memory_mod = sys.modules.get('app.models.memory')
_memory_mod = types.ModuleType('app.models.memory')
_memory_mod.ConversationMemory = MagicMock()
sys.modules['app.models.memory'] = _memory_mod
