#!/bin/bash

# Linux 系统代理切换脚本（支持 WSL）
# 用法：./proxy-toggle.sh on|off|status

PROXY_HOST="172.30.48.1"
PROXY_PORT="7890"

# 检测是否在 WSL 中运行
is_wsl() {
    if grep -qi microsoft /proc/version 2>/dev/null; then
        return 0
    elif grep -qi WSL /proc/version 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 显示_usage
show_usage() {
    echo -e "${YELLOW}用法:${NC} $0 <command>"
    echo ""
    echo "命令:"
    echo "  on      开启系统代理"
    echo "  off     关闭系统代理"
    echo "  status  查看代理状态"
    echo ""
    echo "示例:"
    echo "  $0 on       # 开启代理"
    echo "  $0 off      # 关闭代理"
    echo "  $0 status   # 查看状态"
}

# 开启代理
enable_proxy() {
    echo -e "${GREEN}正在开启系统代理...${NC}"
    
    # 设置当前会话环境变量（立即生效）
    export http_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
    export https_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
    export no_proxy="localhost,127.0.0.1,::1"
    export HTTP_PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
    export HTTPS_PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
    export NO_PROXY="localhost,127.0.0.1,::1"
    
    # 写入 ~/.bashrc 使其永久生效
    if ! grep -q "export http_proxy=\"http://${PROXY_HOST}:${PROXY_PORT}\"" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << EOF

# 系统代理配置 (由 proxy-toggle.sh 添加)
export http_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
export https_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
export no_proxy="localhost,127.0.0.1,::1"
export HTTP_PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
export HTTPS_PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
export NO_PROXY="localhost,127.0.0.1,::1"
EOF
        echo -e "${GREEN}✓ 已写入 ~/.bashrc${NC}"
    else
        echo -e "${YELLOW}! ~/.bashrc 中已存在代理配置${NC}"
    fi
    
    # WSL 环境提示
    if is_wsl; then
        echo -e "${YELLOW}检测到 WSL 环境，跳过 GNOME 系统代理设置${NC}"
    else
        # 尝试设置系统级代理 (需要 sudo)
        if command -v gsettings &> /dev/null; then
            echo -e "${YELLOW}检测到 GNOME 桌面，尝试设置系统级代理...${NC}"
            if sudo gsettings set org.gnome.system.proxy mode 'manual' 2>/dev/null; then
                sudo gsettings set org.gnome.system.proxy.http host "${PROXY_HOST}"
                sudo gsettings set org.gnome.system.proxy.http port "${PROXY_PORT}"
                sudo gsettings set org.gnome.system.proxy.https host "${PROXY_HOST}"
                sudo gsettings set org.gnome.system.proxy.https port "${PROXY_PORT}"
                echo -e "${GREEN}✓ 已设置 GNOME 系统代理${NC}"
            else
                echo -e "${YELLOW}! 无法设置 GNOME 代理 (可能需要 sudo 权限或非 GNOME 环境)${NC}"
            fi
        fi
    fi
    
    # 验证代理
    echo ""
    echo -e "${GREEN}代理已开启!${NC}"
    echo "代理地址：${PROXY_HOST}:${PROXY_PORT}"
    echo ""
    
    # 立即测试代理
    echo -e "${YELLOW}测试代理连接...${NC}"
    if curl -s --connect-timeout 5 -x "http://${PROXY_HOST}:${PROXY_PORT}" https://www.google.com > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Google 可访问（代理工作正常）${NC}"
    else
        echo -e "${RED}✗ Google 无法访问（请检查代理服务器是否运行）${NC}"
    fi
    
    echo ""
    echo "验证命令:"
    echo "  curl -I https://www.google.com"
    echo ""
    echo -e "${GREEN}注意：当前终端会话已生效${NC}"
}

# 关闭代理
disable_proxy() {
    echo -e "${YELLOW}正在关闭系统代理...${NC}"
    
    # 清除当前会话环境变量（立即生效）
    unset http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY
    
    # 从 ~/.bashrc 移除代理配置
    if [ -f ~/.bashrc ]; then
        # 创建备份
        cp ~/.bashrc ~/.bashrc.backup.$(date +%Y%m%d%H%M%S)
        
        # 移除代理配置行
        sed -i '/# 系统代理配置 (由 proxy-toggle.sh 添加)/,/export NO_PROXY=/d' ~/.bashrc 2>/dev/null
        
        # 清理可能残留的空行和旧格式
        sed -i '/^export http_proxy=/d' ~/.bashrc
        sed -i '/^export https_proxy=/d' ~/.bashrc
        sed -i '/^export no_proxy=/d' ~/.bashrc
        sed -i '/^export HTTP_PROXY=/d' ~/.bashrc
        sed -i '/^export HTTPS_PROXY=/d' ~/.bashrc
        sed -i '/^export NO_PROXY=/d' ~/.bashrc
        
        echo -e "${GREEN}✓ 已清理 ~/.bashrc 中的代理配置${NC}"
    fi
    
    # WSL 环境提示
    if is_wsl; then
        echo -e "${YELLOW}检测到 WSL 环境，跳过 GNOME 系统代理设置${NC}"
    else
        # 关闭 GNOME 系统代理
        if command -v gsettings &> /dev/null; then
            echo -e "${YELLOW}检测到 GNOME 桌面，尝试关闭系统级代理...${NC}"
            if sudo gsettings set org.gnome.system.proxy mode 'none' 2>/dev/null; then
                echo -e "${GREEN}✓ 已关闭 GNOME 系统代理${NC}"
            else
                echo -e "${YELLOW}! 无法修改 GNOME 代理设置${NC}"
            fi
        fi
    fi
    
    echo ""
    echo -e "${GREEN}代理已关闭!${NC}"
    echo ""
    echo -e "${GREEN}注意：当前终端会话已生效${NC}"
}

# 查看代理状态
check_status() {
    echo -e "${YELLOW}=== 系统代理状态 ===${NC}"
    echo ""
    
    # 检测环境
    if is_wsl; then
        echo -e "${GREEN}运行环境：${YELLOW}WSL${NC}"
    else
        echo -e "${GREEN}运行环境：${YELLOW}原生 Linux${NC}"
    fi
    echo ""
    
    # 检查环境变量
    echo -e "${GREEN}当前会话环境变量:${NC}"
    if [ -n "$http_proxy" ]; then
        echo -e "  HTTP_PROXY:  ${GREEN}$http_proxy${NC}"
    else
        echo -e "  HTTP_PROXY:  ${RED}未设置${NC}"
    fi
    
    if [ -n "$https_proxy" ]; then
        echo -e "  HTTPS_PROXY: ${GREEN}$https_proxy${NC}"
    else
        echo -e "  HTTPS_PROXY: ${RED}未设置${NC}"
    fi
    
    echo ""
    
    # 检查 ~/.bashrc 配置
    echo -e "${GREEN}~/.bashrc 配置:${NC}"
    if grep -q "export http_proxy=" ~/.bashrc 2>/dev/null; then
        grep "export.*proxy" ~/.bashrc | head -6 | while read line; do
            echo -e "  ${GREEN}$line${NC}"
        done
    else
        echo -e "  ${RED}无代理配置${NC}"
    fi
    
    echo ""
    
    # WSL 环境下跳过 GNOME 检查
    if is_wsl; then
        echo -e "${YELLOW}GNOME 系统代理：${NC}不适用 (WSL 环境)"
    elif command -v gsettings &> /dev/null; then
        echo -e "${GREEN}GNOME 系统代理设置:${NC}"
        proxy_mode=$(gsettings get org.gnome.system.proxy mode 2>/dev/null)
        if [ "$proxy_mode" = "'manual'" ]; then
            proxy_host=$(gsettings get org.gnome.system.proxy.http host 2>/dev/null)
            proxy_port=$(gsettings get org.gnome.system.proxy.http port 2>/dev/null)
            echo -e "  状态：${GREEN}已开启 (手动)${NC}"
            echo -e "  地址：$proxy_host:$proxy_port"
        elif [ "$proxy_mode" = "'none'" ]; then
            echo -e "  状态：${RED}已关闭${NC}"
        else
            echo -e "  状态：${YELLOW}$proxy_mode${NC}"
        fi
    else
        echo -e "${YELLOW}GNOME 系统代理：${NC}未检测到桌面环境"
    fi
    
    echo ""
    
    # 网络连通性测试
    echo -e "${GREEN}网络测试:${NC}"
    if command -v curl &> /dev/null; then
        if curl -s --connect-timeout 3 https://www.baidu.com > /dev/null 2>&1; then
            echo -e "  百度：${GREEN}可访问${NC}"
        else
            echo -e "  百度：${RED}无法访问${NC}"
        fi
        
        if curl -s --connect-timeout 3 https://www.google.com > /dev/null 2>&1; then
            echo -e "  Google: ${GREEN}可访问${NC}"
        else
            echo -e "  Google: ${RED}无法访问${NC}"
        fi
    else
        echo "  (安装 curl 以进行网络测试)"
    fi
    
    echo ""
    
    # 快速诊断
    echo -e "${YELLOW}快速诊断:${NC}"
    if [ -n "$http_proxy" ] && curl -s --connect-timeout 3 -x "$http_proxy" https://www.google.com > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓ 代理工作正常${NC}"
    elif [ -n "$http_proxy" ]; then
        echo -e "  ${RED}✗ 代理已设置但无法连接（检查代理服务器）${NC}"
    else
        echo -e "  ${YELLOW}! 代理未设置（运行 ./proxy-toggle.sh on 开启）${NC}"
    fi
}

# 主程序
case "$1" in
    on)
        enable_proxy
        ;;
    off)
        disable_proxy
        ;;
    status)
        check_status
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit 0
