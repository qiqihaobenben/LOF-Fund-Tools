FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt  -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 复制应用代码
COPY lof3.py .

# 设置环境变量
ENV PORT=5000
ENV DEBUG=False

# 开放端口
EXPOSE 5000

# 运行应用
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "lof3:application"]
