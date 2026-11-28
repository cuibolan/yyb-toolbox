using System.Diagnostics;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class LogcatPage : UserControl
{
    private const int MaxLines = 1500;

    private Process? _proc;
    private bool _running;
    private readonly Queue<string> _lines = new();
    private readonly object _bufferLock = new();
    private int _pending;
    private DispatcherQueueTimer? _timer;

    public LogcatPage()
    {
        InitializeComponent();
        Unloaded += (s, e) => Stop();
    }

    private string Level => (LevelBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "I";

    private async void OnStartClicked(object sender, RoutedEventArgs e)
    {
        if (_running) return;

        var adb = AppState.Current.Adb;
        if (!adb.Ready || adb.State() != "device")
        {
            AppState.Current.SetStatus("引擎未连接，无法抓取日志");
            return;
        }

        // 先清理上一轮可能残留的进程，避免孤儿 logcat 同时刷屏
        KillProc();

        // UI 线程读取控件值，再把纯字符串传给后台线程
        var tag = TagBox.Text?.Trim();
        var level = Level;
        try
        {
            _proc = await Task.Run(() => adb.StartLogcat(string.IsNullOrEmpty(tag) ? null : tag, level));
            _running = true;
            lock (_bufferLock) { _lines.Clear(); _pending = 0; }
            AppState.Current.SetStatus("日志抓取中…");

            _timer = DispatcherQueue.GetForCurrentThread().CreateTimer();
            _timer.Interval = TimeSpan.FromMilliseconds(700);
            _timer.Tick += (_, _) => Flush();
            _timer.Start();

            _ = Task.Run(async () =>
            {
                try
                {
                    var reader = _proc.StandardOutput;
                    while (_running)
                    {
                        var line = await reader.ReadLineAsync();
                        if (line == null) break;
                        lock (_bufferLock)
                        {
                            _lines.Enqueue(line);
                            if (_lines.Count > MaxLines) _lines.Dequeue();
                            _pending++;
                        }
                    }
                }
                catch (Exception ex)
                {
                    AppState.Log($"logcat reader: {ex}");
                }
                _running = false;
            });
        }
        catch (Exception ex)
        {
            KillProc();
            AppState.Log($"logcat start: {ex}");
            var msg = $"{ex.GetType().Name}: {ex.Message}";
            if (ex.InnerException != null)
                msg += $" | 内部: {ex.InnerException.GetType().Name}: {ex.InnerException.Message}";
            AppState.Current.SetStatus($"启动日志失败：{msg}");
        }
    }

    private void OnStopClicked(object sender, RoutedEventArgs e) => Stop();

    private void Stop()
    {
        _running = false;
        _timer?.Stop();
        _timer = null;
        KillProc();
        Flush();
        AppState.Current.SetStatus("日志已停止");
    }

    private void KillProc()
    {
        try { _proc?.Kill(true); } catch { }
        try { _proc?.Dispose(); } catch { }
        _proc = null;
    }

    private void OnClearClicked(object sender, RoutedEventArgs e)
    {
        lock (_bufferLock) { _lines.Clear(); _pending = 0; }
        LogBox.Text = "";
    }

    private void Flush()
    {
        List<string> snapshot;
        lock (_bufferLock)
        {
            if (_pending == 0) return;
            snapshot = _lines.ToList();
            _pending = 0;
        }

        LogBox.Text = string.Join("\n", snapshot);
        LogBox.SelectionStart = LogBox.Text.Length;
    }
}
