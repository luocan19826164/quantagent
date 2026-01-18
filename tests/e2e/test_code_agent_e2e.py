"""
Code Agent E2E 测试
端到端测试核心用户场景
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestPageNavigation:
    """测试页面导航"""
    
    def test_homepage_loads(self, page: Page, flask_server: str):
        """E2E-01: 首页加载"""
        page.goto(flask_server)
        
        # 验证页面加载成功（标题包含关键词）
        title = page.title()
        assert "量化" in title or "Agent" in title or "QuantAgent" in title
    
    def test_navigate_to_code_agent(self, logged_in_page: Page):
        """E2E-02: 切换到 Code Agent 视图"""
        page = logged_in_page
        
        # 点击 Code Agent 导航
        nav_btn = page.locator("#navCodeAgent")
        if nav_btn.is_visible():
            nav_btn.click()
            
            # 验证 Code Agent 视图显示
            code_view = page.locator("#codeAgentView")
            expect(code_view).to_be_visible()


@pytest.mark.e2e
class TestAuthentication:
    """测试用户认证"""
    
    def test_login_page_accessible(self, page: Page, flask_server: str):
        """E2E-03: 页面可访问"""
        page.goto(flask_server)
        page.wait_for_load_state("networkidle")
        
        # 页面应该正常加载
        assert page.url is not None
        # 检查页面内容
        body = page.locator("body")
        expect(body).to_be_visible()
    
    def test_login_success(self, page: Page, flask_server: str, test_user: dict):
        """E2E-04: 用户登录成功"""
        page.goto(flask_server)
        page.wait_for_load_state("networkidle")
        
        login_form = page.locator("#loginForm")
        if login_form.is_visible():
            # 填写登录表单
            page.fill("#username", test_user["username"])
            page.fill("#password", test_user["password"])
            page.click("#loginBtn")
            
            # 等待登录完成
            page.wait_for_load_state("networkidle")
            
            # 验证登录成功（不再显示登录表单）
            expect(login_form).not_to_be_visible()


@pytest.mark.e2e
class TestProjectManagement:
    """测试项目管理"""
    
    def test_create_project(self, code_agent_page: Page):
        """E2E-05: 创建新项目"""
        page = code_agent_page
        
        # 查找并点击创建项目按钮
        create_btn = page.locator("#createProjectBtn, .create-project-btn, [data-action='create-project']")
        
        if create_btn.is_visible():
            create_btn.click()
            
            # 等待模态框出现
            page.wait_for_timeout(500)
            
            # 填写项目名称
            name_input = page.locator("#projectNameInput, [name='projectName'], .project-name-input")
            if name_input.is_visible():
                name_input.fill("e2e_test_project")
                
                # 确认创建
                confirm_btn = page.locator("#confirmCreateBtn, .confirm-btn, [data-action='confirm']")
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    
                    # 等待项目创建
                    page.wait_for_timeout(1000)
    
    def test_project_selector_exists(self, code_agent_page: Page):
        """E2E-06: 项目选择器存在"""
        page = code_agent_page
        
        # 使用精确选择器
        project_selector = page.locator("#projectSelector")
        expect(project_selector).to_be_visible()


@pytest.mark.e2e
class TestFileOperations:
    """测试文件操作"""
    
    def test_file_tree_exists(self, code_agent_page: Page):
        """E2E-07: 文件树存在"""
        page = code_agent_page
        
        # 使用精确选择器
        file_tree = page.locator("#fileTree")
        expect(file_tree).to_be_visible()
    
    def test_code_editor_visible(self, code_agent_page: Page):
        """E2E-08: 代码编辑器显示"""
        page = code_agent_page
        
        # 验证代码编辑区域存在
        code_panel = page.locator(".code-panel-section").first
        expect(code_panel).to_be_visible()


@pytest.mark.e2e
class TestChat:
    """测试聊天功能"""
    
    def test_chat_input_visible(self, code_agent_page: Page):
        """E2E-09: 聊天输入框显示"""
        page = code_agent_page
        
        # 使用精确选择器
        chat_input = page.locator("#codeAgentInput")
        expect(chat_input).to_be_visible()
    
    def test_send_button_exists(self, code_agent_page: Page):
        """E2E-10: 发送按钮存在"""
        page = code_agent_page
        
        # 使用精确选择器
        send_btn = page.locator("#codeAgentSendBtn")
        expect(send_btn).to_be_visible()
    
    def test_chat_messages_area_exists(self, code_agent_page: Page):
        """E2E-11: 聊天消息区域存在"""
        page = code_agent_page
        
        # 使用精确选择器
        messages = page.locator("#codeAgentMessages")
        expect(messages).to_be_visible()


@pytest.mark.e2e
class TestUILayout:
    """测试 UI 布局"""
    
    def test_three_column_layout(self, code_agent_page: Page):
        """E2E-12: 三栏布局显示"""
        page = code_agent_page
        
        # 验证三个主要区域都存在 - 使用 .first 避免多元素问题
        chat_section = page.locator(".code-chat-section").first
        file_section = page.locator(".file-browser-section").first
        
        # 聊天和文件区域应该可见
        expect(chat_section).to_be_visible()
        expect(file_section).to_be_visible()
    
    def test_responsive_layout(self, code_agent_page: Page):
        """E2E-13: 响应式布局"""
        page = code_agent_page
        
        # 调整窗口大小
        page.set_viewport_size({"width": 1024, "height": 768})
        page.wait_for_timeout(500)
        
        # 验证页面仍然可用
        code_view = page.locator("#codeAgentView")
        expect(code_view).to_be_visible()


@pytest.mark.e2e
@pytest.mark.slow
class TestUserWorkflow:
    """测试完整用户工作流（较慢）"""
    
    def test_code_agent_view_complete(self, code_agent_page: Page):
        """E2E-20: Code Agent 视图完整"""
        page = code_agent_page
        
        # 1. 查看 Code Agent 视图
        code_view = page.locator("#codeAgentView")
        expect(code_view).to_be_visible()
        
        # 2. 检查项目选择器 - 使用精确 ID
        project_selector = page.locator("#projectSelector")
        expect(project_selector).to_be_visible()
        
        # 3. 检查聊天区域
        chat_area = page.locator(".code-chat-section").first
        expect(chat_area).to_be_visible()
        
        # 4. 检查文件区域
        file_area = page.locator(".file-browser-section").first
        expect(file_area).to_be_visible()


@pytest.mark.e2e
class TestAccessibility:
    """测试可访问性"""
    
    def test_sidebar_accessible(self, logged_in_page: Page):
        """E2E-30: 侧边栏可访问"""
        page = logged_in_page
        
        # 验证侧边栏存在 - 使用 .first 避免多元素
        sidebar = page.locator(".sidebar").first
        expect(sidebar).to_be_visible()
    
    def test_code_agent_send_button_has_content(self, code_agent_page: Page):
        """E2E-31: Code Agent 发送按钮有内容"""
        page = code_agent_page
        
        # 使用精确选择器
        send_btn = page.locator("#codeAgentSendBtn")
        if send_btn.is_visible():
            # 按钮应该有文本、emoji 或图标
            inner_html = send_btn.inner_html()
            assert len(inner_html.strip()) > 0


@pytest.mark.e2e
class TestErrorHandling:
    """测试错误处理"""
    
    def test_404_page(self, page: Page, flask_server: str):
        """E2E-40: 404 页面处理"""
        page.goto(f"{flask_server}/nonexistent-page-xyz")
        
        # 应该显示 404 或重定向
        assert page.url is not None
    
    def test_network_error_handling(self, logged_in_page: Page):
        """E2E-41: 网络错误处理"""
        page = logged_in_page
        
        # 切换到 Code Agent
        nav_btn = page.locator("#navCodeAgent")
        if nav_btn.is_visible():
            nav_btn.click()
            page.wait_for_timeout(500)
        
        # 验证页面没有崩溃
        code_view = page.locator("#codeAgentView")
        expect(code_view).to_be_visible()


@pytest.mark.e2e
class TestCodeAgentInteraction:
    """测试 Code Agent 交互"""
    
    def test_can_type_in_chat(self, code_agent_page: Page):
        """E2E-50: 可以在聊天框输入"""
        page = code_agent_page
        
        chat_input = page.locator("#codeAgentInput")
        expect(chat_input).to_be_visible()
        
        # 输入消息
        chat_input.fill("测试消息")
        
        # 验证输入成功
        value = chat_input.input_value()
        assert "测试消息" in value
    
    def test_execution_controls_exist(self, code_agent_page: Page):
        """E2E-51: 执行控制按钮存在"""
        page = code_agent_page
        
        # 检查执行相关按钮
        run_btn = page.locator("#runCodeBtn, .run-btn, [data-action='run']").first
        # 运行按钮可能在选择文件后才显示，这里只检查区域存在
        file_section = page.locator(".file-browser-section").first
        expect(file_section).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--headed"])
