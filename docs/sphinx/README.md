# FishAsyncTask 文档

这是 FishAsyncTask 项目的 Sphinx 文档。

## 构建文档

### 安装依赖

```bash
pip install -r requirements.txt
```

### 构建 HTML 文档

```bash
make html
```

构建结果在 `build/html/` 目录。

### 实时预览（开发时使用）

```bash
make livehtml
```

文档会在 `http://127.0.0.1:8000` 自动打开，并在文件修改时自动刷新。

### 清理构建文件

```bash
make clean
```

### 其他格式

- PDF: `make latexpdf`
- EPUB: `make epub`

## 文档结构

```
source/
├── index.rst          # 主页
├── quickstart.rst     # 快速开始
├── advanced.rst       # 高级用法
├── best_practices.rst # 最佳实践
├── faq.rst           # 常见问题
├── config.rst        # 配置参考
├── changelog.rst     # 更新日志
└── api/              # API 文档
    └── index.rst
```

## 部署到 GitHub Pages

构建完成后，将 `build/html/` 目录的内容推送到 `gh-pages` 分支：

```bash
make html
cp -r build/html/* ../
git checkout gh-pages
git merge main
git push origin gh-pages
```
