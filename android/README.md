# Habit Tracker — Native Android App (Kotlin + Jetpack Compose)

原生 Android 客户端（位于 `android/`），使用 **Kotlin**、**Jetpack Compose**、**Material 3**、**OkHttp**、**Kotlinx Serialization** 和 **DataStore Preferences** 构建，直接连接仓库中的 **FastAPI + MongoDB** 后端（`backend/`）。

## 功能特性

- **登录 / 注册与服务器地址配置**：支持配置后端 `Server API URL`（含模拟器 `http://10.0.2.2:8000` 和局域网快捷填入）、JWT 持久化自动登录与过期自动跳转登录。
- **今日打卡 (`今日`)**：按日历切换日期（支持补卡、回到今天）、实时完成进度条、单次与多次目标习惯（`+` / `-`）、每日打卡笔记与连续打卡天数 (`🔥`) 展示。
- **本周 / 本月待办 (`待办`)**：支持切换 `本周` / `本月` 计划视图、前后周期翻页与 `回到当前`、筛选 `待完成` / `漏卡` / `全部`、切换 `按日期` / `按习惯` 视图，并对今天及历史漏卡日期直接打卡或补卡。
- **习惯管理 (`习惯`)**：新建/编辑习惯（名称、备注、目标次数、目标 SLO、6 种主题色、每天 / 按周多选 / 按月例行规则：月初正数 / 月末倒数 / 第 Y 周的周 X、多时段提醒与闹钟设置）、归档/取消归档、切换显示已归档习惯及带二次确认的永久删除。
- **提醒与闹钟 (`AlarmManager` + 通知渠道)**：支持为每个习惯配置多组 `HH:MM` 提醒时间、普通通知或强提醒闹钟铃声渠道、自定义贪睡延时与提示语；支持通知栏直接「立即打卡 / 稍后提醒 / 关闭闹钟」、顶部提醒总览弹窗与一键静音，以及「同步到系统闹钟」和开机/改时自动重排调度。
- **打卡管控模式（Habit Modes）**：支持 `free`（自由打卡）、`strict`（模式1：开始提醒 → 强制执行「开始执行」→ 强制完成）、`window`（模式2：弹性时间窗）、`reminder`（模式3：定时提醒），超时违规提醒、一键超时补卡及与准时完成/连胜/SLI 的独立统计。
- **统计分析 (`统计`)**：最高活跃连胜、30 天平均完成率、今日达成 KPI 卡片、近 7 天柱状图以及习惯连胜排行榜。
- **个人 SLI 看板 (`SLI`)**：基于 `GET /api/stats/sli` 的 SRE 个人习惯分析看板，支持 `7 / 30 / 90` 天窗口切换、整体与分习惯 `target_slo` 配置、错误预算剩余与多窗口燃烧率、滚动 SLI 趋势柱状图及星期可靠性诊断。

## 方式一：通过 GitHub Actions 获取可直接安装的 APK

1. 将代码推送到 GitHub 后，Workflow **`Build Cross-Platform Clients & Test Backend`** 会自动运行 `build-android-native` 任务：
   - 执行 `./gradlew testDebugUnitTest`
   - 编译 `./gradlew assembleDebug`
2. 在 GitHub 仓库 **Actions** 页面打开对应运行记录，在底部 **Artifacts** 下载 **`android-native-apk`**，解压得到 `HabitTracker-Android-debug.apk` 安装到手机或模拟器。

## 方式二：使用 Android Studio 本地运行与编译

1. 使用 **Android Studio**（Ladybug / Meerkat 或更新版本，自带 JDK 17）直接打开 `android/` 目录。
2. 等待 Gradle 同步完成（如需命令行构建，可在 `android/` 目录执行 `.\gradlew.bat testDebugUnitTest assembleDebug`）。
3. 启动后端服务后，在登录页填写对应地址：
   - **Android 模拟器**：使用默认地址 `http://10.0.2.2:8000`（已配置 `usesCleartextTraffic="true"` 允许本地 HTTP 调试）。
   - **真机测试（同一 Wi-Fi）**：填写运行后端电脑的局域网 IP，例如 `http://192.168.1.50:8000`（后端启动时需加 `--host 0.0.0.0`）。
