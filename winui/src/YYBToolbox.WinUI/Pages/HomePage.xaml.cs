using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Models;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class HomePage : UserControl
{
    public HomePage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (AppState.Current.Info != null)
            ShowInfo(AppState.Current.Info);
    }

    private async void OnRefreshClicked(object sender, RoutedEventArgs e)
    {
        AppState.Current.SetStatus("正在采集设备信息…");
        try
        {
            var info = await AppState.Current.CollectInfoAsync();
            AppState.Current.Info = info;
            ShowInfo(info);
            AppState.Current.SetStatus("设备信息已刷新");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"采集失败：{ex.Message}");
        }
    }

    private void ShowInfo(DeviceInfo info)
    {
        ModelLine.Text = $"{info.Brand} · {info.Model}";
        AndroidLine.Text = $"Android {info.Android}（SDK {info.Sdk}）";
        AbiLine.Text = info.Abi;
        ResolutionLine.Text = $"{info.Resolution} · {info.Density} dpi";
        StorageLine.Text = info.Storage;
        MemoryLine.Text = info.Memory;
        BatteryLine.Text = info.Battery;
        UptimeLine.Text = info.Uptime;
        SelinuxLine.Text = info.Selinux;
        RootLine.Text = info.Root ? $"已 Root · {info.Magisk}" : "未 Root";
        SerialLine.Text = info.Serial;
    }
}
