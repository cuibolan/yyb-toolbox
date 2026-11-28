using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.Storage.Pickers;
using YYBToolbox.WinUI.Models;
using YYBToolbox.WinUI.Services;

namespace YYBToolbox.WinUI.Pages;

public sealed partial class FilesPage : UserControl
{
    private string _current = "/sdcard";
    private bool _rootMode;
    private FileEntry? Selected => FileList.SelectedItem as FileEntry;

    public FilesPage()
    {
        InitializeComponent();
        Loaded += async (s, e) => await LoadDirAsync(_current);
    }

    private async Task LoadDirAsync(string path)
    {
        var adb = AppState.Current.Adb;
        if (!adb.Ready || adb.State() != "device")
        {
            AppState.Current.SetStatus("引擎未连接，无法浏览文件");
            return;
        }
        _current = AdbClient.NormalizeRemote(path);
        PathBox.Text = _current;
        AppState.Current.SetStatus($"正在列出 {_current} …");
        try
        {
            var entries = await Task.Run(() => adb.ListDir(_current, _rootMode));
            FileList.ItemsSource = entries;
            AppState.Current.SetStatus($"目录 {_current}：{entries.Count} 项");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"浏览目录失败：{ex.Message}");
        }
    }

    private void OnUpClicked(object sender, RoutedEventArgs e)
    {
        if (_current == "/") return;
        _ = LoadDirAsync(AdbClient.RemoteParent(_current));
    }

    private void OnGoClicked(object sender, RoutedEventArgs e) => _ = LoadDirAsync(PathBox.Text?.Trim() ?? "/");
    private void OnRefreshClicked(object sender, RoutedEventArgs e) => _ = LoadDirAsync(_current);

    private void OnRootToggleChanged(object sender, RoutedEventArgs e)
    {
        _rootMode = RootToggle.IsChecked == true;
        _ = LoadDirAsync(_current);
    }

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs e) { }

    private async void OnItemDoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if (Selected is not { } entry) return;
        var remote = AppState.Current.Adb.JoinRemote(_current, entry.Name);

        if (entry.IsDir)
        {
            _ = LoadDirAsync(remote);
            return;
        }

        if (entry.Type == "链接")
        {
            AppState.Current.SetStatus($"正在判断 {entry.Name} 是不是目录 …");
            try
            {
                var isDir = await Task.Run(() => AppState.Current.Adb.IsRemoteDir(remote, _rootMode));
                if (isDir)
                {
                    _ = LoadDirAsync(remote);
                    return;
                }
            }
            catch (Exception ex)
            {
                AppState.Current.SetStatus($"无法判断链接类型：{ex.Message}");
                return;
            }
        }

        OnPullClicked(sender, e);
    }

    private async void OnPullClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { IsDir: false } entry) { await DialogHelper.InfoAsync(XamlRoot, "拉取", "请选中一个文件（目录暂不支持批量拉取）"); return; }
        try
        {
            var remote = AppState.Current.Adb.JoinRemote(_current, entry.Name);
            var ext = Path.GetExtension(entry.Name);
            if (string.IsNullOrWhiteSpace(ext)) ext = ".bin";
            var picker = new FileSavePicker { SuggestedFileName = AdbClient.SanitizeWindowsName(entry.Name) };
            picker.FileTypeChoices.Add("文件", new List<string> { ext });
            WinRT.Interop.InitializeWithWindow.Initialize(picker, AppState.Current.WindowHandle);
            var file = await picker.PickSaveFileAsync();
            if (file == null) return;

            AppState.Current.SetStatus("正在拉取文件…");
            await Task.Run(() => AppState.Current.Adb.PullFile(remote, file.Path, rootMode: _rootMode));
            AppState.Current.SetStatus($"已拉取到：{file.Path}");
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"拉取失败：{ex.Message}");
        }
    }

    private async void OnPushClicked(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, AppState.Current.WindowHandle);
        var files = await picker.PickMultipleFilesAsync();
        if (files == null || files.Count == 0) return;

        foreach (var file in files)
        {
            var remote = AppState.Current.Adb.JoinRemote(_current, file.Name);
            AppState.Current.SetStatus($"正在推送 {file.Name}…");
            try
            {
                await Task.Run(() => AppState.Current.Adb.PushFile(file.Path, remote));
                AppState.Current.SetStatus($"已推送：{remote}");
            }
            catch (Exception ex)
            {
                AppState.Current.SetStatus($"推送失败 {file.Name}：{ex.Message}");
            }
        }
        _ = LoadDirAsync(_current);
    }

    private async void OnDeleteClicked(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } entry) return;
        var remote = AppState.Current.Adb.JoinRemote(_current, entry.Name);
        if (!await DialogHelper.ConfirmAsync(XamlRoot, "删除", $"删除 {remote}？{(entry.IsDir ? "（递归删除目录）" : "")}")) return;
        try
        {
            AppState.Current.SetStatus("正在删除…");
            await Task.Run(() => AppState.Current.Adb.RemovePath(remote, entry.IsDir, _rootMode));
            AppState.Current.SetStatus("删除完成");
            _ = LoadDirAsync(_current);
        }
        catch (Exception ex)
        {
            AppState.Current.SetStatus($"删除失败：{ex.Message}");
        }
    }
}
