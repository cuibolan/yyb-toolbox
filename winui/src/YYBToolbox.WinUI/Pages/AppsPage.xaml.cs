using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using YYBToolbox.WinUI.Models;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class AppsPage : UserControl
{
    private List<AppInfo> _apps = new();
    private AppInfo? Selected => AppList.SelectedItem as AppInfo;

    public AppsPage()
    {
        InitializeComponent();
        Loaded += async (s, e) => await RefreshAsync();
    }

    // UI 线程读取，避免后台线程访问 XAML 对象
    private string CurrentScope() => (ScopeBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "第三方";

    private async Task RefreshAsync()
    {
        var adb = AppState.Current.Adb;
        if (!adb.Ready) { AppState.Current.SetStatus("未找到 adb.exe，请到「系统设置」指定路径"); return; }
        if (adb.State() != "device") { AppState.Current.SetStatus("引擎未连接，先点顶部「连接引擎」"); return; }

        var scope = CurrentScope();
        AppState.Current.SetStatus($"正在读取{scope}应用列表…");
        try
        {
            var list = await Task.Run(() => adb.ListPackages(scope));
            _apps = list;
            ApplyFilter();
            AppState.Current.SetStatus($"共 {_apps.Count} 个应用");
        }
        catch (Exception ex)
        {
            _apps = new List<AppInfo>();
            ApplyFilter();
            AppState.Current.SetStatus($"读取应用失败：{ex.GetType().Name} {ex.Message}");
        }
    }

    private void ApplyFilter()
    {
        var kw = SearchBox.Text?.Trim().ToLowerInvariant() ?? "";
        var filtered = string.IsNullOrEmpty(kw)
            ? _apps
            : _apps.Where(a => a.Package.ToLowerInvariant().Contains(kw)).ToList();
        AppList.ItemsSource = filtered;
    }

    private void OnScopeChanged(object sender, SelectionChangedEventArgs e) => _ = RefreshAsync();

    private void OnFilterTextChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args) => ApplyFilter();

    private void OnFilterSubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args) => ApplyFilter();

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs e) { }

    private async void OnRefreshClicked(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async void OnLaunchClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } a) return;
        await RunAction("启动", () => AppState.Current.Adb.StartPackage(a.Package));
    }

    private async void OnStopClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } a) return;
        await RunAction("停止", () => AppState.Current.Adb.ForceStop(a.Package));
    }

    private async void OnClearClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } a) return;
        if (!await DialogHelper.ConfirmAsync(XamlRoot, "清除数据", $"清除 {a.Package} 的全部数据？")) return;
        await RunAction("清除数据", () => AppState.Current.Adb.ClearData(a.Package));
    }

    private async void OnToggleClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } a) return;
        var disable = a.State != "已禁用";
        await RunAction(disable ? "禁用" : "启用", () =>
        {
            if (disable) AppState.Current.Adb.Disable(a.Package);
            else AppState.Current.Adb.Enable(a.Package);
        });
        await RefreshAsync();
    }

    private async void OnUninstallClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } a) return;
        if (!await DialogHelper.ConfirmAsync(XamlRoot, "卸载应用", $"卸载 {a.Package}？")) return;
        await RunAction("卸载", () => AppState.Current.Adb.Uninstall(a.Package));
        await RefreshAsync();
    }

    private async void OnExportClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } a) return;
        try
        {
            AppState.Current.SetStatus("正在定位 APK 路径…");
            var remote = await Task.Run(() => AppState.Current.Adb.PackagePath(a.Package));
            if (string.IsNullOrEmpty(remote)) { await DialogHelper.InfoAsync(XamlRoot, "导出失败", "未找到该应用的 APK 路径"); return; }

            var picker = new FileSavePicker { SuggestedFileName = AdbClient.SanitizeWindowsName(a.Package) + ".apk" };
            picker.FileTypeChoices.Add("APK 安装包", new List<string> { ".apk" });
            WinRT.Interop.InitializeWithWindow.Initialize(picker, AppState.Current.WindowHandle);
            var file = await picker.PickSaveFileAsync();
            if (file == null) return;

            AppState.Current.SetStatus("正在导出 APK…");
            await Task.Run(() => AppState.Current.Adb.PullFile(remote, file.Path, rootMode: true));
            AppState.Current.SetStatus($"已导出：{file.Path}");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"导出失败：{ex.Message}");
        }
    }

    private async void OnInstallClicked(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".apk");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, AppState.Current.WindowHandle);
        var files = await picker.PickMultipleFilesAsync();
        if (files == null || files.Count == 0) return;

        foreach (var file in files)
        {
            AppState.Current.SetStatus($"正在安装 {file.Name}…");
            try
            {
                await Task.Run(() => AppState.Current.Adb.InstallApk(file.Path));
                AppState.Current.SetStatus($"安装完成：{file.Name}");
            }
            catch (Exception ex)
            {
                AppState.Current.SetStatus($"安装失败 {file.Name}：{ex.Message}");
            }
        }
        await RefreshAsync();
    }

    private async Task RunAction(string label, Action action)
    {
        try
        {
            AppState.Current.SetStatus($"{label}中…");
            await Task.Run(action);
            AppState.Current.SetStatus($"{label}完成");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"{label}失败：{ex.Message}");
            await DialogHelper.InfoAsync(XamlRoot, $"{label}失败", ex.Message);
        }
    }
}
