using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using YYBToolbox.WinUI.Pages;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI;

public sealed partial class MainWindow : Window
{
    private const string ShellVersion = "1.3.4.0";
    private readonly Dictionary<string, Type> _pages = new()
    {
        ["home"] = typeof(HomePage),
        ["apps"] = typeof(AppsPage),
        ["files"] = typeof(FilesPage),
        ["shell"] = typeof(ShellPage),
        ["logcat"] = typeof(LogcatPage),
        ["shot"] = typeof(ShotPage),
        ["settings"] = typeof(SettingsPage),
        ["diag"] = typeof(DiagPage),
        ["microg"] = typeof(MicrogPage),
        ["root"] = typeof(RootPage),
    };

    public MainWindow()
    {
        InitializeComponent();
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1280, 820));
        AppState.Current.WindowHandle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        VersionBadge.Text = $"v{ShellVersion}";
        StatusBar.Text = "就绪";

        AppState.Current.StatusChanged += text =>
            DispatcherQueue.TryEnqueue(() => StatusBar.Text = text);

        NavView.Loaded += (s, e) => NavView.SelectedItem = NavView.MenuItems.First();
    }

    private void OnNavSelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is NavigationViewItem { Tag: string tag })
            Navigate(tag);
    }

    private void Navigate(string tag)
    {
        if (ContentFrame == null || !_pages.TryGetValue(tag, out var type)) return;
        try
        {
            ContentFrame.Content = (UIElement)Activator.CreateInstance(type)!;
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"页面 {tag} 加载失败：{ex.Message}");
        }
    }

    private async void OnConnectClicked(object sender, RoutedEventArgs e)
    {
        ConnectButton.IsEnabled = false;
        ConnState.Text = "正在连接…";
        AppState.Current.SetStatus("正在连接引擎…");
        try
        {
            var serial = await AppState.Current.ConnectAsync();
            AppState.Current.Info = await AppState.Current.CollectInfoAsync();
            ConnState.Text = $"已连接 {serial}";
            AppState.Current.SetStatus($"已连接 {serial}");
            Navigate("home");
        }
        catch (Exception ex)
        {
            ConnState.Text = "连接失败";
            AppState.Current.SetStatus($"连接失败：{ex.Message}");
            await ShowDialog("连接失败", ex.Message);
        }
        finally
        {
            ConnectButton.IsEnabled = true;
        }
    }

    private async Task ShowDialog(string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            CloseButtonText = "确定",
            XamlRoot = ContentFrame.XamlRoot,
        };
        await dialog.ShowAsync();
    }
}
