using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class SettingsPage : UserControl
{
    public SettingsPage()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        AdbPathBox.Text = AppState.Current.Config.AdbPath;
        SerialBox.Text = AppState.Current.Config.Serial;
    }

    private async void OnBrowseAdbClicked(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".exe");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, AppState.Current.WindowHandle);
        var file = await picker.PickSingleFileAsync();
        if (file != null) AdbPathBox.Text = file.Path;
    }

    private void OnSaveClicked(object sender, RoutedEventArgs e)
    {
        AppState.Current.Config.AdbPath = AdbPathBox.Text?.Trim() ?? "";
        AppState.Current.Config.Serial = string.IsNullOrWhiteSpace(SerialBox.Text)
            ? AdbClient.DefaultSerial
            : SerialBox.Text.Trim();
        AppState.Current.Config.Save();
        AppState.Current.RefreshAdb();
        AppState.Current.SetStatus("配置已保存，已按新设置重建 adb 连接");
    }

    private void OnResetClicked(object sender, RoutedEventArgs e)
    {
        AdbPathBox.Text = "";
        SerialBox.Text = AdbClient.DefaultSerial;
    }
}
