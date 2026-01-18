## 前后端联调

1. 使用 `cd /Users/qzj/Desktop/Development/CookHero && source .venv/bin/activate && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ./uvicorn.log 2>&1)"` 启动后端服务。

2. 直接使用playwright在浏览器中打开 `http://localhost:5173/` 进行测试，并访问日志文件 `./uvicorn.log` 查看后端日志。根据输出信息修改前端或后端代码进行联调。(如果需要登录，登录账号为'Decade', 密码为'111')

3. 直到所有功能联调完成且无误后，使用 `kill -9 $(lsof -ti tcp:8000)` 停止后端服务。