using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class LogcatPage : UserControl
{
    private Process? _proc;
    private bool _running;

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

        var tag = TagBox.Text?.Trim();
        try
        {
            _proc = await Task.Run(() => adb.StartLogcat(string.IsNullOrEmpty(tag) ? null : tag, Level));
            _running = true;
            AppState.Current.SetStatus("日志抓取中…");
            _ = Task.Run(async () =>
            {
                var reader = _proc.StandardOutput;
                while (_running && !reader.EndOfStream)
                {
                    var line = await reader.ReadLineAsync();
                    if (line == null) break;
                    DispatcherQueue.TryEnqueue(() => Append(line));
                }
                _running = false;
            });
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"启动日志失败：{ex.Message}");
        }
    }

    private void OnStopClicked(object sender, RoutedEventArgs e) => Stop();

    private void Stop()
    {
        _running = false;
        try { _proc?.Kill(true); } catch { }
        try { _proc?.Dispose(); } catch { }
        _proc = null;
        AppState.Current.SetStatus("日志已停止");
    }

    private void OnClearClicked(object sender, RoutedEventArgs e) => LogBox.Text = "";

    private void Append(string line)
    {
        LogBox.Text += line + "\n";
        LogBox.SelectionStart = LogBox.Text.Length;
    }
}
