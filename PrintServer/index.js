const express = require('express');
const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');
const unixPrint = require('unix-print');

const app = express();
app.use(express.json());

const PORT = 3000;
const REFUND_RATE = 0.10; // 10 cents per container

const COLUMN_WIDTH_12_FONT = 36
const COLUMN_WIDTH_14_FONT = 31

// unixPrint.getPrinters().then((printers) => {
//     console.log(printers);
// });

const divider = (length) => {
    return '-'.repeat(length);
};

app.post('/print-receipt', async (req, res) => {
    try {
        const { totalCount, categories } = req.body;
        const refundTotal = (totalCount * REFUND_RATE).toFixed(2);
        
        // Create a new PDF document
        const doc = new PDFDocument({
            size: 'A6',
            margins: { left: 17, right: 17, top: 50, bottom: 20 }
        });
        const filePath = path.join(__dirname, 'temp-receipt.pdf');
        const writeStream = fs.createWriteStream(filePath);
        
        // Pipe PDF to writeStream
        doc.pipe(writeStream);
        
        // Add company logo (using a placeholder rectangle for this example)
        doc.image('recyclorobo-logo.png', (doc.page.width - 200) / 2, 20, { width: 200 })
        doc.moveDown()
        
        // Add container categories
        doc.font('Roboto_Mono/RobotoMono-VariableFont_wght.ttf').fontSize(12);
        for (const [category, count] of Object.entries(categories)) {
            const dividerWidth = COLUMN_WIDTH_12_FONT - category.length - count.toLocaleString().length - 2
            doc.text(`${category} ${divider(dividerWidth)} ${count}`);
        }

        const totalDividerWidth = COLUMN_WIDTH_14_FONT - 'Total'.length - totalCount.toLocaleString().length - 2
        const totalRefundDividerWidth = COLUMN_WIDTH_14_FONT - 'Total Refund'.length - refundTotal.length - 3

        const time = new Date()
        const dateString = time.toLocaleDateString()
        const timeString = time.toLocaleTimeString()
        const dateDividerWidth = COLUMN_WIDTH_12_FONT - 'Date'.length - dateString.length - 2
        const timeDividerWidth = COLUMN_WIDTH_12_FONT - 'Time'.length - timeString.length - 2
        doc.moveDown()
            .font('Roboto_Mono/static/RobotoMono-Bold.ttf').fontSize(14)
            .text(`Total ${divider(totalDividerWidth)} ${totalCount}`)
            .text(`Total Refund ${divider(totalRefundDividerWidth)} $${refundTotal}`, { bold: true })
            .moveDown()
            .font('Roboto_Mono/RobotoMono-VariableFont_wght.ttf').fontSize(12)
            .text(`Date ${divider(dateDividerWidth)} ${dateString}`)
            .text(`Time ${divider(timeDividerWidth)} ${timeString}`)
            .moveDown()
            .text(`Thank you for recycling!`, { align: 'center' });
        

        doc.moveDown().image('recyclorobo-qrcode.png', (doc.page.width - 100) / 2, doc.y, { width: 100 })

        // Finalize PDF
        doc.end();
        
        // Wait for PDF to finish writing
        writeStream.on('finish', async () => {
            try {
                // Print the PDF
                await unixPrint.print(filePath, 'EPSON_TM-T20II');
                
                // // Clean up temporary file
                // fs.unlinkSync(filePath);
                
                res.json({
                    success: true,
                    message: 'Receipt printed successfully',
                    refundTotal
                });
            } catch (printError) {
                res.status(500).json({
                    success: false,
                    message: 'Error printing receipt',
                    error: printError.message
                });
            }
        });
        
    } catch (error) {
        console.log(error);
        res.status(500).json({
            success: false,
            message: 'Error generating receipt',
            error: error.message
        });
    }
});

app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});