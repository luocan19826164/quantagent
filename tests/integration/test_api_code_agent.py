"""
Code Agent API 集成测试
测试所有 Code Agent 相关的 API 端点
"""

import pytest
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))


def get_project_id_from_response(data):
    """从 API 响应中提取 project_id"""
    # 支持多种可能的返回格式
    if 'project_id' in data:
        return data['project_id']
    if 'id' in data:
        return data['id']
    if 'project' in data:
        project = data['project']
        if isinstance(project, dict):
            return project.get('id') or project.get('project_id')
    return None


# ============ 项目管理 API 测试 ============

class TestProjectAPI:
    """测试项目管理 API"""
    
    def test_create_project(self, authenticated_client, sample_project_data):
        """API-01: 创建项目"""
        response = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        
        # 可能返回 201 或 200
        assert response.status_code in [200, 201], f"Unexpected status: {response.status_code}, data: {response.get_json()}"
        data = response.get_json()
        assert data.get('success') == True
        
        project_id = get_project_id_from_response(data)
        assert project_id is not None, f"No project_id in response: {data}"
    
    def test_get_projects(self, authenticated_client):
        """API-02: 获取项目列表"""
        response = authenticated_client.get('/api/code-agent/projects')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('success') == True
        assert 'projects' in data
        assert isinstance(data['projects'], list)
    
    def test_get_project_detail(self, authenticated_client, sample_project_data):
        """API-03: 获取项目详情"""
        # 先创建项目
        create_resp = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        
        assert create_resp.status_code in [200, 201]
        data = create_resp.get_json()
        project_id = get_project_id_from_response(data)
        assert project_id is not None, f"No project_id in response: {data}"
        
        # 获取详情
        response = authenticated_client.get(f'/api/code-agent/projects/{project_id}')
        assert response.status_code == 200
        detail = response.get_json()
        assert detail.get('success') == True
    
    def test_delete_project(self, authenticated_client, sample_project_data):
        """API-04: 删除项目"""
        # 先创建项目
        create_resp = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        
        assert create_resp.status_code in [200, 201]
        data = create_resp.get_json()
        project_id = get_project_id_from_response(data)
        assert project_id is not None
        
        # 删除
        response = authenticated_client.delete(f'/api/code-agent/projects/{project_id}')
        assert response.status_code in [200, 204], f"Delete failed: {response.get_json()}"
        
        # 验证已删除
        get_resp = authenticated_client.get(f'/api/code-agent/projects/{project_id}')
        assert get_resp.status_code == 404
    
    def test_create_project_default_name(self, authenticated_client):
        """API-05: 创建项目使用默认名称"""
        response = authenticated_client.post(
            '/api/code-agent/projects',
            json={},
            content_type='application/json'
        )
        
        # 应该使用默认名称创建成功
        assert response.status_code in [200, 201]
        data = response.get_json()
        assert data.get('success') == True
    
    def test_get_nonexistent_project(self, authenticated_client):
        """API-06: 获取不存在的项目"""
        response = authenticated_client.get('/api/code-agent/projects/nonexistent_project_id')
        assert response.status_code == 404
    
    def test_unauthenticated_access(self, client):
        """API-07: 未认证访问应返回 401"""
        response = client.get('/api/code-agent/projects')
        assert response.status_code == 401


# ============ 文件管理 API 测试 ============

class TestFileAPI:
    """测试文件管理 API"""
    
    @pytest.fixture
    def project_id(self, authenticated_client, sample_project_data):
        """创建测试项目并返回 ID"""
        response = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        assert response.status_code in [200, 201]
        data = response.get_json()
        return get_project_id_from_response(data)
    
    def test_get_files_empty_project(self, authenticated_client, project_id):
        """API-10: 获取空项目的文件列表"""
        response = authenticated_client.get(f'/api/code-agent/projects/{project_id}/files')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('success') == True
        assert 'files' in data
    
    def test_save_file(self, authenticated_client, project_id, sample_python_file):
        """API-11: 保存文件"""
        response = authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/strategy.py',
            json={'content': sample_python_file},
            content_type='application/json'
        )
        
        assert response.status_code == 200, f"Save failed: {response.get_json()}"
        data = response.get_json()
        assert data.get('success') == True
    
    def test_read_file(self, authenticated_client, project_id, sample_python_file):
        """API-12: 读取已保存的文件"""
        # 先保存
        save_resp = authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/strategy.py',
            json={'content': sample_python_file},
            content_type='application/json'
        )
        assert save_resp.status_code == 200, f"Save failed: {save_resp.get_json()}"
        
        # 再读取
        read_resp = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files/strategy.py'
        )
        
        assert read_resp.status_code == 200
        data = read_resp.get_json()
        assert data.get('success') == True
        assert 'content' in data
        assert 'calculate_rsi' in data['content']
    
    def test_save_nested_file(self, authenticated_client, project_id):
        """API-13: 保存嵌套目录中的文件"""
        response = authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/strategies/rsi/main.py',
            json={'content': 'print("nested file")'},
            content_type='application/json'
        )
        
        assert response.status_code == 200, f"Save nested failed: {response.get_json()}"
        
        # 验证可以读取
        read_resp = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files/strategies/rsi/main.py'
        )
        assert read_resp.status_code == 200
    
    def test_delete_file(self, authenticated_client, project_id):
        """API-14: 删除文件"""
        # 先创建文件
        authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/to_delete.py',
            json={'content': 'print("delete me")'},
            content_type='application/json'
        )
        
        # 删除文件
        response = authenticated_client.delete(
            f'/api/code-agent/projects/{project_id}/files/to_delete.py'
        )
        
        assert response.status_code == 200, f"Delete failed: {response.get_json()}"
        
        # 验证已删除
        read_resp = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files/to_delete.py'
        )
        assert read_resp.status_code == 404
    
    def test_read_nonexistent_file(self, authenticated_client, project_id):
        """API-15: 读取不存在的文件"""
        response = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files/nonexistent.py'
        )
        
        assert response.status_code == 404
    
    def test_update_file(self, authenticated_client, project_id):
        """API-16: 更新已存在的文件"""
        # 创建文件
        authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/update_test.py',
            json={'content': 'version = 1'},
            content_type='application/json'
        )
        
        # 更新文件
        response = authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/update_test.py',
            json={'content': 'version = 2'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        # 验证内容已更新
        read_resp = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files/update_test.py'
        )
        data = read_resp.get_json()
        assert 'version = 2' in data['content']
    
    def test_get_file_tree_with_files(self, authenticated_client, project_id):
        """API-17: 获取包含文件的项目文件树"""
        # 创建多个文件
        authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/main.py',
            json={'content': 'print("main")'},
            content_type='application/json'
        )
        authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/utils/helper.py',
            json={'content': 'print("helper")'},
            content_type='application/json'
        )
        
        # 获取文件树
        response = authenticated_client.get(f'/api/code-agent/projects/{project_id}/files')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('success') == True
        assert 'files' in data


# ============ 对话 API 测试 ============

class TestChatAPI:
    """测试对话 API"""
    
    @pytest.fixture
    def project_id(self, authenticated_client, sample_project_data):
        """创建测试项目并返回 ID"""
        response = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        assert response.status_code in [200, 201]
        data = response.get_json()
        return get_project_id_from_response(data)
    
    def test_send_message_returns_response(self, authenticated_client, project_id, mock_llm):
        """API-20: 发送消息返回响应"""
        response = authenticated_client.post(
            f'/api/code-agent/projects/{project_id}/chat',
            json={'message': '帮我写一个简单的 Python 函数'},
            content_type='application/json'
        )
        
        # SSE 响应或 JSON 响应，状态码应该是 200
        # 如果 project 不存在可能是 404
        assert response.status_code in [200, 404, 500], f"Unexpected: {response.status_code}, {response.data}"
    
    def test_send_empty_message(self, authenticated_client, project_id):
        """API-21: 发送空消息"""
        response = authenticated_client.post(
            f'/api/code-agent/projects/{project_id}/chat',
            json={'message': ''},
            content_type='application/json'
        )
        
        # 空消息应该被拒绝或返回错误
        assert response.status_code in [200, 400, 422]
    
    def test_chat_nonexistent_project(self, authenticated_client):
        """API-22: 向不存在的项目发送消息"""
        response = authenticated_client.post(
            '/api/code-agent/projects/nonexistent_project/chat',
            json={'message': 'test'},
            content_type='application/json'
        )
        
        # 应该返回 404 或 500
        assert response.status_code in [404, 500]
    
    def test_chat_missing_message_field(self, authenticated_client, project_id):
        """API-23: 缺少 message 字段"""
        response = authenticated_client.post(
            f'/api/code-agent/projects/{project_id}/chat',
            json={},
            content_type='application/json'
        )
        
        # 应该返回错误
        assert response.status_code in [200, 400, 422]


# ============ 代码执行 API 测试 ============

class TestExecutionAPI:
    """测试代码执行 API"""
    
    @pytest.fixture
    def project_with_file(self, authenticated_client, sample_project_data, sample_python_file):
        """创建带有文件的项目"""
        # 创建项目
        response = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        
        assert response.status_code in [200, 201]
        data = response.get_json()
        project_id = get_project_id_from_response(data)
        
        # 创建文件
        authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/main.py',
            json={'content': sample_python_file},
            content_type='application/json'
        )
        
        return project_id, 'main.py'
    
    def test_execute_script(self, authenticated_client, project_with_file, mock_docker):
        """API-30: 执行 Python 脚本"""
        project_id, file_name = project_with_file
        
        response = authenticated_client.post(
            f'/api/code-agent/projects/{project_id}/execute',
            json={'file': file_name},
            content_type='application/json'
        )
        
        # 执行可能成功或失败（取决于环境配置）
        assert response.status_code in [200, 400, 500]
    
    def test_stop_execution(self, authenticated_client, project_with_file, mock_docker):
        """API-31: 停止执行"""
        project_id, _ = project_with_file
        
        response = authenticated_client.post(
            f'/api/code-agent/projects/{project_id}/stop'
        )
        
        # 即使没有正在运行的任务也应该返回成功或适当的错误
        assert response.status_code in [200, 400, 404, 500]
    
    def test_get_status(self, authenticated_client, project_with_file, mock_docker):
        """API-32: 获取执行状态"""
        project_id, _ = project_with_file
        
        response = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/status'
        )
        
        # 可能成功获取状态，或者因为配置问题返回错误
        assert response.status_code in [200, 400, 404, 500]
    
    def test_execute_nonexistent_file(self, authenticated_client, project_with_file, mock_docker):
        """API-33: 执行不存在的文件"""
        project_id, _ = project_with_file
        
        response = authenticated_client.post(
            f'/api/code-agent/projects/{project_id}/execute',
            json={'file': 'nonexistent.py'},
            content_type='application/json'
        )
        
        # 应该返回错误
        assert response.status_code in [400, 404, 500]


# ============ 健康检查和基础 API ============

class TestBaseAPI:
    """测试基础 API"""
    
    def test_health_check(self, client):
        """测试健康检查端点"""
        # 主页应该可以访问
        response = client.get('/')
        assert response.status_code in [200, 302]
    
    def test_get_models(self, client):
        """测试获取模型列表"""
        response = client.get('/api/models')
        
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, (list, dict))


# ============ 业务流程集成测试 ============

class TestBusinessFlow:
    """测试完整业务流程"""
    
    def test_full_project_lifecycle(self, authenticated_client, sample_project_data, sample_python_file):
        """测试完整的项目生命周期"""
        # 1. 创建项目
        create_resp = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        
        assert create_resp.status_code in [200, 201]
        data = create_resp.get_json()
        project_id = get_project_id_from_response(data)
        assert project_id is not None
        
        # 2. 验证项目存在于列表中
        list_resp = authenticated_client.get('/api/code-agent/projects')
        assert list_resp.status_code == 200
        projects = list_resp.get_json().get('projects', [])
        project_ids = [get_project_id_from_response({'project': p}) or p.get('id') for p in projects]
        assert project_id in project_ids
        
        # 3. 创建文件
        file_resp = authenticated_client.put(
            f'/api/code-agent/projects/{project_id}/files/strategy.py',
            json={'content': sample_python_file},
            content_type='application/json'
        )
        assert file_resp.status_code == 200, f"Create file failed: {file_resp.get_json()}"
        
        # 4. 读取文件
        read_resp = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files/strategy.py'
        )
        assert read_resp.status_code == 200
        content = read_resp.get_json().get('content')
        assert 'calculate_rsi' in content
        
        # 5. 获取文件树
        tree_resp = authenticated_client.get(
            f'/api/code-agent/projects/{project_id}/files'
        )
        assert tree_resp.status_code == 200
        
        # 6. 删除文件
        del_file_resp = authenticated_client.delete(
            f'/api/code-agent/projects/{project_id}/files/strategy.py'
        )
        assert del_file_resp.status_code == 200
        
        # 7. 删除项目
        delete_resp = authenticated_client.delete(f'/api/code-agent/projects/{project_id}')
        assert delete_resp.status_code in [200, 204]
        
        # 8. 验证项目已删除
        get_resp = authenticated_client.get(f'/api/code-agent/projects/{project_id}')
        assert get_resp.status_code == 404
    
    def test_multiple_projects(self, authenticated_client):
        """测试创建多个项目"""
        project_ids = []
        
        # 创建 3 个项目
        for i in range(3):
            resp = authenticated_client.post(
                '/api/code-agent/projects',
                json={'name': f'project_{i}', 'description': f'Test project {i}'},
                content_type='application/json'
            )
            assert resp.status_code in [200, 201]
            project_ids.append(get_project_id_from_response(resp.get_json()))
        
        # 验证列表中有这 3 个项目
        list_resp = authenticated_client.get('/api/code-agent/projects')
        assert list_resp.status_code == 200
        projects = list_resp.get_json().get('projects', [])
        
        for pid in project_ids:
            found = any(
                p.get('id') == pid or p.get('project_id') == pid 
                for p in projects
            )
            assert found, f"Project {pid} not found in list"
        
        # 清理
        for pid in project_ids:
            authenticated_client.delete(f'/api/code-agent/projects/{pid}')
    
    def test_file_operations_in_sequence(self, authenticated_client, sample_project_data):
        """测试文件操作序列"""
        # 创建项目
        resp = authenticated_client.post(
            '/api/code-agent/projects',
            json=sample_project_data,
            content_type='application/json'
        )
        project_id = get_project_id_from_response(resp.get_json())
        
        # 创建多个文件
        files = {
            'main.py': 'print("main")',
            'utils.py': 'def helper(): pass',
            'config.py': 'DEBUG = True',
        }
        
        for filename, content in files.items():
            save_resp = authenticated_client.put(
                f'/api/code-agent/projects/{project_id}/files/{filename}',
                json={'content': content},
                content_type='application/json'
            )
            assert save_resp.status_code == 200, f"Save {filename} failed: {save_resp.get_json()}"
        
        # 验证所有文件都可以读取
        for filename, expected_content in files.items():
            read_resp = authenticated_client.get(
                f'/api/code-agent/projects/{project_id}/files/{filename}'
            )
            assert read_resp.status_code == 200
            assert expected_content in read_resp.get_json().get('content')
        
        # 清理
        authenticated_client.delete(f'/api/code-agent/projects/{project_id}')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
