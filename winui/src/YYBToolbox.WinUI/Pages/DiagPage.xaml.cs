using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class DiagPage : UserControl
{
    public DiagPage()
    {
        InitializeComponent();
    }

    private async void OnRunClicked(object sender, RoutedEventArgs e)
    {
        var adb = AppState.Current.Adb;
        var lines = new List<string> { "=== 诊断结果 ===" };
        AppState.Current.SetStatus("正在运行诊断…");

        await Task.Run(() =>
        {
            lines.Add($"adb 路径：{(adb.Ready ? adb.Exe : "未找到")}");
            try
            {
                var devices = adb.Devices();
                lines.Add($"已识别设备：{devices.Count}");
                foreach (var d in devices)
                    lines.Add($"  - {string.Join(" / ", d.Select(kv => $"{kv.Key}={kv.Value}"))}");
            }
            catch (Exception ex) { lines.Add($"设备列表读取失败：{ex.Message}"); }

            try { lines.Add($"当前序列号：{adb.Serial}，状态：{adb.State()}"); }
            catch (Exception ex) { lines.Add($"状态读取失败：{ex.Message}"); }

            try { lines.Add($"SELinux：{adb.Shell("getenforce", timeout: 15).Trim()}"); }
            catch (Exception ex) { lines.Add($"SELinux 读取失败：{ex.Message}"); }

            try
            {
                var su = adb.Shell("which su", timeout: 15).Trim();
                lines.Add(string.IsNullOrEmpty(su) ? "Root：未检测到 su" : $"Root：su -> {su}");
            }
            catch (Exception ex) { lines.Add($"Root 检测失败：{ex.Message}"); }
        });

        DiagBox.Text = string.Join("\n", lines);
        AppState.Current.SetStatus("诊断完成");
    }
}
