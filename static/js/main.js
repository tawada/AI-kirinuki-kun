// 処理状況を確認する関数（結果ページが非同期処理の場合に使用）
function checkProcessingStatus(sessionId) {
    fetch(`/status/${sessionId}`)
        .then(response => response.json())
        .then(data => {
            // 処理状況の更新
            updateProcessingUI(data);
            
            // 処理が終了していなければ、再度状態を確認
            if (data.status !== 'completed') {
                setTimeout(() => checkProcessingStatus(sessionId), 2000);
            } else {
                // 処理完了の場合、UIを更新
                showCompletedUI();
            }
        })
        .catch(error => {
            console.error('処理状況の確認でエラーが発生しました:', error);
        });
}

// 処理状況に応じてUIを更新する関数
function updateProcessingUI(data) {
    const statusElement = document.getElementById('processing-status');
    const progressElement = document.getElementById('processing-progress');
    
    if (statusElement && progressElement) {
        statusElement.textContent = data.message;
        progressElement.style.width = `${data.progress}%`;
        progressElement.setAttribute('aria-valuenow', data.progress);
    }
}

// 処理完了後のUI表示
function showCompletedUI() {
    const processingContainer = document.getElementById('processing-container');
    const resultContainer = document.getElementById('result-container');
    
    if (processingContainer && resultContainer) {
        processingContainer.classList.add('d-none');
        resultContainer.classList.remove('d-none');
    }
}

// URL検証
function validateYoutubeUrl(url) {
    const regex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+$/;
    return regex.test(url);
}

// フォーム送信前の検証
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('video-form');
    
    if (form) {
        form.addEventListener('submit', function(e) {
            const urlInput = document.getElementById('youtube_url');
            
            if (urlInput && !validateYoutubeUrl(urlInput.value)) {
                e.preventDefault();
                alert('有効なYouTube URLを入力してください');
                return false;
            }
        });
    }
});