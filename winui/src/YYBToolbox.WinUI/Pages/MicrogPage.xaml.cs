using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class MicrogPage : UserControl
{
    public MicrogPage()
    {
        InitializeComponent();
    }

    private async void OnCheckClicked(object sender, RoutedEventArgs e)
    {
        var adb = AppState.Current.Adb;
        if (!adb.Ready || adb.State() != "device")
        {
            AppState.Current.SetStatus("引擎未连接，无法检查 MicroG 包");
            return;
        }
        try
        {
            AppState.Current.SetStatus("正在检查 MicroG 相关包…");
            var raw = await Task.Run(() => adb.Shell("pm list packages", timeout: 30));
            var keywords = new[] { "microg", "gms", "gsf", "fakegapps", "gproxy" };
            var matched = raw.Split('\n')
                .Select(l => l.Trim())
                .Where(l => l.StartsWith("package:") && keywords.Any(k => l.Contains(k, StringComparison.OrdinalIgnoreCase)))
                .ToList();
            ResultBox.Text = matched.Count == 0
                ? "未检测到 MicroG / GmsCore / GsfProxy / FakeGApps 相关包。"
                : string.Join("\n", matched);
            AppState.Current.SetStatus($"检测到 {matched.Count} 个相关包");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"检查失败：{ex.Message}");
        }
    }
}
