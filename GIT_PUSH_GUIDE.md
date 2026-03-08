# 🚀 Git 推送指南

## 📋 前置条件

你的系统需要先安装 Git。请按以下步骤操作：

### 1. 安装 Git

#### Windows 用户
1. 访问 https://git-scm.com/download/win
2. 下载 Git for Windows
3. 运行安装程序，使用默认设置
4. 安装完成后重启命令行

#### 验证安装
```bash
git --version
```

### 2. 配置 Git 用户信息
```bash
git config --global user.name "你的用户名"
git config --global user.email "你的邮箱"
```

## 🔧 推送代码到 GitHub

### 步骤 1: 初始化本地仓库
```bash
cd d:\dev\windsurf
git init
```

### 步骤 2: 添加远程仓库
```bash
git remote add origin https://github.com/sddxac/ai-stock-vibe.git
```

### 步骤 3: 创建 .gitignore 文件
```bash
# 创建 .gitignore 文件，忽略不需要的文件
echo "# Python" > .gitignore
echo "__pycache__/" >> .gitignore
echo "*.py[cod]" >> .gitignore
echo "*$py.class" >> .gitignore
echo "*.so" >> .gitignore
echo ".Python" >> .gitignore
echo "build/" >> .gitignore
echo "develop-eggs/" >> .gitignore
echo "dist/" >> .gitignore
echo "downloads/" >> .gitignore
echo "eggs/" >> .gitignore
echo ".eggs/" >> .gitignore
echo "lib/" >> .gitignore
echo "lib64/" >> .gitignore
echo "parts/" >> .gitignore
echo "sdist/" >> .gitignore
echo "var/" >> .gitignore
echo "wheels/" >> .gitignore
echo "*.egg-info/" >> .gitignore
echo ".installed.cfg" >> .gitignore
echo "*.egg" >> .gitignore
echo "" >> .gitignore
echo "# Virtual environments" >> .gitignore
echo "venv/" >> .gitignore
echo "env/" >> .gitignore
echo ".venv/" >> .gitignore
echo "" >> .gitignore
echo "# IDE" >> .gitignore
echo ".vscode/" >> .gitignore
echo ".idea/" >> .gitignore
echo "*.swp" >> .gitignore
echo "*.swo" >> .gitignore
echo "" >> .gitignore
echo "# OS" >> .gitignore
echo ".DS_Store" >> .gitignore
echo "Thumbs.db" >> .gitignore
echo "" >> .gitignore
echo "# Logs" >> .gitignore
echo "*.log" >> .gitignore
echo "" >> .gitignore
echo "# Streamlit" >> .gitignore
echo ".streamlit/secrets.toml" >> .gitignore
```

### 步骤 4: 添加所有文件到暂存区
```bash
git add .
```

### 步骤 5: 提交代码
```bash
git commit -m "Initial commit: AI Stock Analysis App with Authentication"
```

### 步骤 6: 推送到 GitHub
```bash
git branch -M main
git push -u origin main
```

## 🔐 GitHub 认证

如果推送时需要认证，你有几个选项：

### 选项 1: Personal Access Token (推荐)
1. 访问 GitHub Settings > Developer settings > Personal access tokens
2. 生成新的 token（选择 repo 权限）
3. 使用 token 作为密码

### 选项 2: SSH Key
```bash
# 生成 SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"

# 添加到 SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# 复制 public key 到 GitHub
cat ~/.ssh/id_ed25519.pub
```

然后使用 SSH URL：
```bash
git remote set-url origin git@github.com:sddxac/ai-stock-vibe.git
```

## 📁 推送的文件结构

你的仓库将包含以下文件：

```
ai-stock-vibe/
├── StockAnalyser.py              # 主应用文件
├── auth_system.py              # 认证系统（生产版）
├── auth_system_mock.py         # 认证系统（模拟版）
├── requirements.txt            # 依赖包列表
├── DEPLOYMENT_GUIDE.md        # 部署指南
├── AUTH_SYSTEM_README.md       # 认证系统说明
├── .streamlit/
│   └── secrets.toml           # 配置文件（已忽略）
├── test_*.py                 # 测试文件
└── setup_*.py                # 设置脚本
```

## 🚀 部署到 Streamlit Cloud

推送完成后，你可以：

1. 访问 https://share.streamlit.io/
2. 点击 "New app"
3. 连接你的 GitHub 仓库
4. 选择 `StockAnalyser.py` 作为主文件
5. 配置环境变量：
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
6. 点击 "Deploy"

## 🔄 后续更新

更新代码后：
```bash
git add .
git commit -m "你的提交信息"
git push
```

## 📝 注意事项

1. **不要提交敏感信息**：`.streamlit/secrets.toml` 已在 .gitignore 中
2. **定期备份**：GitHub 就是你的备份
3. **分支管理**：开发时可以创建功能分支
4. **提交信息**：使用清晰、有意义的提交信息

---

**完成这些步骤后，你的代码就成功推送到 GitHub 了！** 🎉

如果遇到问题，请检查：
- Git 是否正确安装
- 网络连接是否正常
- GitHub 认证是否配置正确
- 仓库 URL 是否正确
