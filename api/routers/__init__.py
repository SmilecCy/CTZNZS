# -*- coding: utf-8 -*-
"""api.routers 包：路由模块。

【这个包里有什么】

    auth.py    认证相关路由（注册、登录、登出）
    user.py    用户端路由（出题、作答、错题集）
    admin.py   后台端路由（课程、资料、预热、题库、自检）

【路由为什么不放在 main.py】

    如果全放 main.py，一个文件会超过 2000 行，很难维护。
    按"使用者"拆分（用户 vs 后台）比按"资源"拆（course vs material）
    更合理——因为权限模型是按使用者分的：
      - /api/user/*  只让学生访问
      - /api/admin/* 只让管理员访问
"""