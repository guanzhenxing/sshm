#!/bin/bash
# ============================================================
# sshm 安装/卸载脚本
#
# 用法：
#   ./install.sh          — 安装 wrapper 脚本到 ~/.local/bin
#   ./install.sh wrapper  — 同上
#   ./install.sh pyinstaller — PyInstaller 打包并安装独立二进制
#   ./install.sh uninstall   — 卸载
#
# 默认安装到用户空间（~/.local），无需 sudo。
# 如需系统级安装，用 sudo 运行本脚本。
# ============================================================

set -e

# 检测：以 root/sudo 运行则安装到系统目录，否则用户目录
if [ "$(id -u)" = "0" ]; then
    PREFIX="/usr/local"
else
    PREFIX="$HOME/.local"
fi

BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/share/sshm"    # onedir bundle 目录
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="$BIN_DIR/sshm"

# ── wrapper 脚本方式 ──────────────────────────────
# 优点：简单，改代码立即生效
# 缺点：依赖源码目录和 .venv 不被移动/删除

install_wrapper() {
    echo "📦 安装 wrapper 脚本到 $WRAPPER ..."
    mkdir -p "$BIN_DIR"
    cat > "$WRAPPER" << EOF
#!/bin/bash
# sshm — SSH Server Manager
# 由 install.sh 自动生成，请勿手动编辑
exec $SOURCE_DIR/.venv/bin/python -m sshm "\$@"
EOF
    chmod +x "$WRAPPER"
    echo "✅ 已安装。现在可以在任意终端运行: sshm"
}

# ── PyInstaller 打包方式 ──────────────────────────
# 优点：独立二进制，不依赖源码，可拷贝到其他 Mac
# 缺点：每次改代码需要重新打包
#
# 用 --onedir（非 --onefile）：onefile 每次启动都要把 ~29MB
# 解压到临时目录，实测冷启动 ~9s；onedir 把库摊在磁盘上，启动
# 与 wrapper 持平（~70ms）。代价：装出来是 bundle 目录而非单文件。
# bundle 装到 $LIB_DIR，再软链可执行文件到 $WRAPPER。

install_pyinstaller() {
    echo "📦 检查 PyInstaller ..."
    if ! "$SOURCE_DIR/.venv/bin/python" -c "import PyInstaller" 2>/dev/null; then
        echo "   安装 PyInstaller ..."
        "$SOURCE_DIR/.venv/bin/pip" install pyinstaller
    fi

    echo "🔨 打包中（--onedir）..."
    cd "$SOURCE_DIR"
    "$SOURCE_DIR/.venv/bin/pyinstaller" \
        --onedir \
        --name sshm \
        --clean \
        --noconfirm \
        src/sshm/__main__.py

    echo "📥 安装 bundle 到 $LIB_DIR，软链到 $WRAPPER ..."
    rm -rf "$LIB_DIR"
    mkdir -p "$LIB_DIR" "$BIN_DIR"
    cp -R "$SOURCE_DIR/dist/sshm/." "$LIB_DIR/"
    chmod +x "$LIB_DIR/sshm"
    ln -sf "$LIB_DIR/sshm" "$WRAPPER"

    echo "✅ 已安装独立二进制。现在可以在任意终端运行: sshm"
    echo "   目录大小: $(du -sh "$LIB_DIR" | cut -f1)"
}

# ── 卸载 ──────────────────────────────────────────

uninstall() {
    # 软链（onedir）或旧 onefile 单文件都一并清理
    if [ -e "$WRAPPER" ] || [ -L "$WRAPPER" ]; then
        rm -f "$WRAPPER"
        echo "✅ 已卸载 $WRAPPER"
    else
        echo "ℹ️  $WRAPPER 不存在，无需卸载"
    fi
    if [ -d "$LIB_DIR" ]; then
        rm -rf "$LIB_DIR"
        echo "✅ 已移除 bundle 目录 $LIB_DIR"
    fi
    # 兼容此前 sudo 安装到 /usr/local 的旧版本清理
    OLD_WRAPPER="/usr/local/bin/sshm"
    OLD_BUNDLE="/usr/local/lib/sshm"
    if [ -e "$OLD_WRAPPER" ] || [ -L "$OLD_WRAPPER" ]; then
        echo "⚠️  发现旧系统级安装 $OLD_WRAPPER，需要 sudo 清理，请手动执行："
        echo "   sudo rm -f $OLD_WRAPPER"
    fi
    if [ -d "$OLD_BUNDLE" ]; then
        echo "   sudo rm -rf $OLD_BUNDLE"
    fi
}

# ── 主逻辑 ────────────────────────────────────────

case "${1:-}" in
    uninstall|remove)
        uninstall
        ;;
    pyinstaller|binary)
        install_pyinstaller
        ;;
    wrapper|"")
        install_wrapper
        ;;
    *)
        echo "用法: $0 [wrapper|pyinstaller|uninstall]"
        echo ""
        echo "  (无参数)         — 安装 wrapper 脚本（默认）"
        echo "  wrapper          — 安装 wrapper 脚本"
        echo "  pyinstaller      — PyInstaller 打包（--onedir）并安装独立二进制"
        echo "  uninstall        — 卸载"
        echo ""
        echo "  安装路径: $BIN_DIR"
        echo "  运行脚本: $WRAPPER"
        echo "  (以 root/sudo 运行本脚本可安装到 /usr/local)"
        exit 1
        ;;
esac
