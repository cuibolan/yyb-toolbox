using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class RootPage : UserControl
{
    public RootPage()
    {
        InitializeComponent();
    }

    private async void OnCheckClicked(object sender, RoutedEventArgs e)
    {
        var adb = AppState.Current.Adb;
        if (!adb.Ready || adb.State() != "device")
        {
            AppState.Current.SetStatus("引擎未连接，无法检测 Root 状态");
            return;
        }
        var lines = new List<string>();
        try
        {
            await Task.Run(() =>
            {
                var whichSu = adb.Shell("which su", timeout: 15).Trim();
                lines.Add(string.IsNullOrEmpty(whichSu) ? "su：未找到" : $"su：{whichSu}");

                var id = adb.Shell("su -c id", timeout: 15).Trim();
                lines.Add(string.IsNullOrEmpty(id) ? "su -c id：失败（无 Root 或 su 不可用）" : $"su -c id：{id}");

                var magisk = adb.Shell("pm list packages | grep -i magisk", timeout: 15).Trim();
                lines.Add(string.IsNullOrEmpty(magisk) ? "Magisk 应用：未检测到" : $"Magisk：{magisk}");
            });
            ResultBox.Text = string.Join("\n", lines);
            AppState.Current.SetStatus("Root 状态检测完成");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"检测失败：{ex.Message}");
        }
    }
}
