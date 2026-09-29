# -*- coding: utf-8 -*-
"""api 包：HTTP 接口层。

【分层说明】

    api/ 是"接口层"，只做三件事：
      1. 接收 HTTP 请求
      2. 调 app/ 业务层做实际工作
      3. 把结果转成 HTTP 响应

    **绝不写业务逻辑。** 所有业务都在 app/ 层。

【为什么这一层要单独存在】

    没有它的话，前端要直接调 Python 函数——
    但 React 跑在浏览器里，Python 跑在服务器上，跨进程。

    接口层就是它们之间的桥：React 发 HTTP 请求，FastAPI 收，
    调 app/ai/、app/database/ 等，返回 JSON，React 拿到数据渲染页面。
"""