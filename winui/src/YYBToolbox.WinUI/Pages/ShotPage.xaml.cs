using System.Runtime.InteropServices.WindowsRuntime;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Pickers;
using Windows.Storage.Streams;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class ShotPage : UserControl
{
    private byte[]? _png;
    private string? _shotPath;

    public ShotPage()
    {
        InitializeComponent();
    }

    private async void OnShotClicked(object sender, RoutedEventArgs e)
    {
        var adb = AppState.Current.Adb;
        if (!adb.Ready || adb.State() != "device")
        {
            AppState.Current.SetStatus("引擎未连接，无法截图");
            return;
        }
        try
        {
            AppState.Current.SetStatus("正在截图…");
            _png = await Task.Run(() => adb.Screenshot());
            if (_png == null || _png.Length == 0)
            {
                AppState.Current.SetStatus("截图结果为空");
                return;
            }
            await LoadImageAsync(_png);

            // 对齐原版：截图后自动落到默认 screenshots 目录
            Directory.CreateDirectory(ConfigService.ShotDir);
            _shotPath = Path.Combine(ConfigService.ShotDir, $"shot_{DateTime.Now:yyyyMMdd_HHmmss}.png");
            await File.WriteAllBytesAsync(_shotPath, _png);
            AppState.Current.SetStatus($"截图完成，{_png.Length / 1024} KB，已保存：{_shotPath}");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"截图失败：{ex.Message}");
        }
    }

    private async Task LoadImageAsync(byte[] png)
    {
        var stream = new InMemoryRandomAccessStream();
        await stream.WriteAsync(png.AsBuffer());
        stream.Seek(0);
        var bmp = new BitmapImage();
        await bmp.SetSourceAsync(stream);
        ShotImage.Source = bmp;
    }

    private async void OnSaveClicked(object sender, RoutedEventArgs e)
    {
        if (_png == null || _png.Length == 0)
        {
            await DialogHelper.InfoAsync(XamlRoot, "保存", "还没有截图，请先截取当前屏幕");
            return;
        }
        var picker = new FileSavePicker { SuggestedFileName = $"screenshot_{DateTime.Now:yyyyMMdd_HHmmss}.png" };
        picker.FileTypeChoices.Add("PNG 图片", new List<string> { ".png" });
        WinRT.Interop.InitializeWithWindow.Initialize(picker, AppState.Current.WindowHandle);
        var file = await picker.PickSaveFileAsync();
        if (file == null) return;

        try
        {
            await File.WriteAllBytesAsync(file.Path, _png);
            AppState.Current.SetStatus($"截图已保存：{file.Path}");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"保存失败：{ex.Message}");
        }
    }
}
